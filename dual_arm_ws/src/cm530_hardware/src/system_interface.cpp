#include "cm530_hardware/system_interface.hpp"

#include <cmath>
#include <exception>
#include <format>
#include <limits>
#include <stdexcept>

#include "cm530_hardware/posix_serial.hpp"
#include "hardware_interface/types/hardware_interface_type_values.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "rclcpp/rclcpp.hpp"

namespace cm530_hardware
{
namespace
{

// AX-12A counts as the v19 firmware reported them, for display only. raw_target is
// NaN until the firmware has acknowledged an AX for that arm. raw_load is the
// Present Load from the same READ, signed (CCW positive), 1023 = maximum torque.
constexpr const char * kRawPositionInterface = "raw_position";
constexpr const char * kRawTargetInterface = "raw_target";
constexpr const char * kRawLoadInterface = "raw_load";

std::string join(const std::array<std::uint16_t, kJointsPerArm> & values)
{
  return std::format("{},{},{},{}", values[0], values[1], values[2], values[3]);
}

std::string describe(const Compliance & compliance)
{
  return std::format(
    "margin {} slope {} punch {}", join(compliance.margin), join(compliance.slope), join(compliance.punch));
}

bool parse_bool(const std::string & text, const std::string & name)
{
  if (text == "true") {
    return true;
  }
  if (text == "false") {
    return false;
  }
  throw std::runtime_error(std::format("{} must be true or false, got '{}'", name, text));
}

std::chrono::milliseconds optional_ms(
  const hardware_interface::HardwareInfo & info, const std::string & name,
  std::chrono::milliseconds fallback)
{
  const auto found = info.hardware_parameters.find(name);
  if (found == info.hardware_parameters.end()) {
    return fallback;
  }
  const int value = std::stoi(found->second);
  if (value <= 0) {
    throw std::runtime_error(std::format("{} must be positive", name));
  }
  return std::chrono::milliseconds{value};
}

double optional_double(
  const hardware_interface::HardwareInfo & info, const std::string & name, double fallback)
{
  const auto found = info.hardware_parameters.find(name);
  if (found == info.hardware_parameters.end()) {
    return fallback;
  }
  const double value = std::stod(found->second);
  if (!std::isfinite(value) || value <= 0.0) {
    throw std::runtime_error(std::format("{} must be positive", name));
  }
  return value;
}

}  // namespace

CM530SystemInterface::CallbackReturn CM530SystemInterface::on_init(
  const hardware_interface::HardwareComponentInterfaceParams & params)
{
  if (SystemInterface::on_init(params) != CallbackReturn::SUCCESS) {
    return CallbackReturn::ERROR;
  }
  try {
    port_ = info_.hardware_parameters.at("port");
    calibration_file_ = info_.hardware_parameters.at("calibration_file");
    // Optional: empty or absent leaves every motor at its power-up compliance.
    if (const auto found = info_.hardware_parameters.find("motor_settings_file");
      found != info_.hardware_parameters.end())
    {
      motor_settings_file_ = found->second;
    }
    enable_motion_ = parse_bool(info_.hardware_parameters.at("enable_motion"), "enable_motion");
    command_timeout_ = optional_ms(info_, "command_timeout_ms", command_timeout_);
    startup_listen_ = optional_ms(info_, "startup_listen_ms", startup_listen_);
    feedback_stale_ = optional_ms(info_, "feedback_stale_ms", feedback_stale_);
    speed_options_.gain = optional_double(info_, "speed_gain", speed_options_.gain);
    speed_options_.catch_up_s =
      std::chrono::duration<double>(optional_ms(info_, "speed_catch_up_ms", std::chrono::milliseconds{250})).count();
    speed_options_.min_speed = static_cast<int>(optional_double(info_, "speed_min", speed_options_.min_speed));
    speed_options_.max_speed = static_cast<int>(optional_double(info_, "speed_max", speed_options_.max_speed));
    if (speed_options_.min_speed < kMinSpeed || speed_options_.max_speed > kMaxSpeed ||
      speed_options_.min_speed > speed_options_.max_speed)
    {
      throw std::runtime_error(
        std::format("speed_min and speed_max must satisfy {} <= min <= max <= {}", kMinSpeed, kMaxSpeed));
    }
  } catch (const std::exception & error) {
    RCLCPP_ERROR(get_logger(), "Invalid hardware parameters: %s", error.what());
    return CallbackReturn::ERROR;
  }

  if (info_.joints.size() != kJointCount) {
    RCLCPP_ERROR(get_logger(), "Expected %zu joints, got %zu", kJointCount, info_.joints.size());
    return CallbackReturn::ERROR;
  }
  for (std::size_t index = 0; index < kJointCount; ++index) {
    const auto & joint = info_.joints[index];
    if (joint.name != kJointNames[index]) {
      RCLCPP_ERROR(
        get_logger(), "Joint %zu is '%s', expected '%s'", index, joint.name.c_str(),
        std::string{kJointNames[index]}.c_str());
      return CallbackReturn::ERROR;
    }
    const bool interfaces_ok =
      joint.command_interfaces.size() == 1 &&
      joint.command_interfaces[0].name == hardware_interface::HW_IF_POSITION &&
      joint.state_interfaces.size() == 5 &&
      joint.state_interfaces[0].name == hardware_interface::HW_IF_POSITION &&
      joint.state_interfaces[1].name == hardware_interface::HW_IF_VELOCITY &&
      joint.state_interfaces[2].name == kRawPositionInterface &&
      joint.state_interfaces[3].name == kRawTargetInterface &&
      joint.state_interfaces[4].name == kRawLoadInterface;
    if (!interfaces_ok) {
      RCLCPP_ERROR(
        get_logger(), "Joint '%s' needs position command and position, velocity, %s, %s, %s state",
        joint.name.c_str(), kRawPositionInterface, kRawTargetInterface, kRawLoadInterface);
      return CallbackReturn::ERROR;
    }
    position_state_[index] = joint.name + "/" + hardware_interface::HW_IF_POSITION;
    velocity_state_[index] = joint.name + "/" + hardware_interface::HW_IF_VELOCITY;
    raw_position_state_[index] = joint.name + "/" + kRawPositionInterface;
    raw_target_state_[index] = joint.name + "/" + kRawTargetInterface;
    raw_load_state_[index] = joint.name + "/" + kRawLoadInterface;
    position_command_[index] = joint.name + "/" + hardware_interface::HW_IF_POSITION;
  }
  return CallbackReturn::SUCCESS;
}

bool CM530SystemInterface::require_ok(const LinkResult & result, const std::string & action)
{
  if (result.ok()) {
    return true;
  }
  RCLCPP_ERROR(get_logger(), "%s failed: %s", action.c_str(), result.detail.c_str());
  return false;
}

void CM530SystemInterface::publish_positions(
  const std::array<RawPose, kArmCount> & poses,
  const std::array<std::optional<RawPose>, kArmCount> & targets)
{
  for (std::size_t index = 0; index < kJointCount; ++index) {
    const std::size_t arm = index / kJointsPerArm;
    const std::size_t joint = index % kJointsPerArm;
    const int raw = poses[arm][joint];
    last_rad_[index] = calibration_->raw_to_rad(index, raw);
    set_state(position_state_[index], last_rad_[index]);
    set_state(velocity_state_[index], 0.0);
    set_state(raw_position_state_[index], static_cast<double>(raw));
    set_state(raw_load_state_[index], static_cast<double>(signed_load(latest_load_[arm][joint])));
    set_state(
      raw_target_state_[index],
      targets[arm] ? static_cast<double>((*targets[arm])[joint]) : std::numeric_limits<double>::quiet_NaN());
  }
}

CM530SystemInterface::CallbackReturn CM530SystemInterface::on_configure(const rclcpp_lifecycle::State &)
{
  try {
    calibration_ = Calibration::from_file(calibration_file_);
    motor_settings_.reset();
    if (!motor_settings_file_.empty()) {
      motor_settings_ = MotorSettings::from_file(motor_settings_file_);
    }
    if (enable_motion_) {
      const auto blockers = calibration_->motion_blockers(is_pseudo_terminal(port_));
      if (!blockers.empty()) {
        for (const auto & blocker : blockers) {
          RCLCPP_ERROR(get_logger(), "Motion refused: %s", blocker.c_str());
        }
        return CallbackReturn::ERROR;
      }
    }
    link_ = std::make_unique<Link>(std::make_unique<PosixSerial>(port_), command_timeout_);
  } catch (const std::exception & error) {
    RCLCPP_ERROR(get_logger(), "Configuration refused: %s", error.what());
    return CallbackReturn::ERROR;
  }

  if (!require_ok(link_->handshake(startup_listen_), "Handshake")) {
    release_link();
    return CallbackReturn::ERROR;
  }
  for (const Arm arm : kArms) {
    const std::string name{arm_name(arm)};
    const LinkResult home = link_->transact(Command::get_home(arm));
    if (!require_ok(home, "GET_HOME " + name)) {
      release_link();
      return CallbackReturn::ERROR;
    }
    if (home.pose != calibration_->expected_home(arm)) {
      RCLCPP_ERROR(get_logger(), "Board HOME for %s differs from the calibration: %s", name.c_str(), home.detail.c_str());
      release_link();
      return CallbackReturn::ERROR;
    }
    const LinkResult read = link_->transact(Command::read(arm));
    if (!require_ok(read, "READ " + name) || !read.pose || !read.load) {
      release_link();
      return CallbackReturn::ERROR;
    }
    latest_raw_[static_cast<std::size_t>(arm)] = *read.pose;
    latest_load_[static_cast<std::size_t>(arm)] = *read.load;
    // Reads only: what the motors hold now, and their supply and temperature.
    const LinkResult compliance = link_->transact(Command::get_compliance(arm));
    const LinkResult diag = link_->transact(Command::diag(arm));
    if (!require_ok(compliance, "GET_COMP " + name) || !compliance.compliance ||
      !require_ok(diag, "DIAG " + name) || !diag.diagnostics)
    {
      release_link();
      return CallbackReturn::ERROR;
    }
    RCLCPP_INFO(
      get_logger(), "%s compliance now: %s; voltage %s (0.1 V), temperature %s C", name.c_str(),
      describe(*compliance.compliance).c_str(), join(diag.diagnostics->voltage).c_str(),
      join(diag.diagnostics->temperature).c_str());
  }
  acked_target_ = {};
  publish_positions(latest_raw_, acked_target_);
  RCLCPP_INFO(
    get_logger(), "CM-530 connected on %s (%s)", port_.c_str(),
    enable_motion_ ? "motion authorized" : "read-only");
  return CallbackReturn::SUCCESS;
}

CM530SystemInterface::CallbackReturn CM530SystemInterface::on_activate(const rclcpp_lifecycle::State &)
{
  if (!link_ || !link_->healthy()) {
    RCLCPP_ERROR(get_logger(), "Activation refused: serial link is not healthy");
    return CallbackReturn::ERROR;
  }
  for (const Arm arm : kArms) {
    const std::string name{arm_name(arm)};
    const LinkResult read = link_->transact(Command::read(arm));
    if (!require_ok(read, "READ " + name) || !read.pose || !read.load) {
      return CallbackReturn::ERROR;
    }
    latest_raw_[static_cast<std::size_t>(arm)] = *read.pose;
    latest_load_[static_cast<std::size_t>(arm)] = *read.load;
  }
  if (enable_motion_) {
    // Limits are never widened to fit: the first write would fault anyway, so
    // refuse before torque is applied to either arm.
    bool inside_limits = true;
    for (const Arm arm : kArms) {
      for (const auto & violation : calibration_->pose_limit_violations(arm, latest_raw_[static_cast<std::size_t>(arm)])) {
        RCLCPP_ERROR(get_logger(), "Activation refused, move the arm by hand first: %s", violation.c_str());
        inside_limits = false;
      }
    }
    if (!inside_limits) {
      return CallbackReturn::ERROR;
    }
    // Compliance before torque, read back before trusting it. The registers are
    // RAM, so this runs at every activation; a motor power cycle resets them.
    if (motor_settings_) {
      for (const Arm arm : kArms) {
        const std::string name{arm_name(arm)};
        const Compliance & wanted = motor_settings_->arms[static_cast<std::size_t>(arm)];
        if (!require_ok(link_->transact(Command::set_compliance(arm, wanted)), "COMP " + name)) {
          return CallbackReturn::ERROR;
        }
        const LinkResult check = link_->transact(Command::get_compliance(arm));
        if (!require_ok(check, "GET_COMP " + name) || !check.compliance) {
          return CallbackReturn::ERROR;
        }
        if (*check.compliance != wanted) {
          RCLCPP_ERROR(
            get_logger(), "Activation refused: %s compliance reads %s, wanted %s", name.c_str(),
            describe(*check.compliance).c_str(), describe(wanted).c_str());
          return CallbackReturn::ERROR;
        }
        RCLCPP_INFO(get_logger(), "%s compliance set: %s", name.c_str(), describe(wanted).c_str());
      }
    }
    for (const Arm arm : kArms) {
      const std::string name{arm_name(arm)};
      // The firmware requires a target before torque, so hold the measured pose.
      if (!require_ok(link_->transact(Command::ax(arm, latest_raw_[static_cast<std::size_t>(arm)])), "AX " + name) ||
        !require_ok(link_->transact(Command::torque_enable(arm, true)), "TORQUE on " + name))
      {
        return CallbackReturn::ERROR;
      }
      // OK,AX: the firmware accepted the measured pose as this arm's target.
      acked_target_[static_cast<std::size_t>(arm)] = latest_raw_[static_cast<std::size_t>(arm)];
    }
  }
  publish_positions(latest_raw_, acked_target_);
  for (std::size_t index = 0; index < kJointCount; ++index) {
    set_command(position_command_[index], last_rad_[index]);
  }
  fault_logged_ = false;
  have_last_command_ = false;
  const auto now = std::chrono::steady_clock::now();
  last_stamp_.fill(now);
  SchedulerOptions options;
  options.enable_motion = enable_motion_;
  options.max_step_raw = calibration_->max_step_raw();
  options.speed = speed_options_;
  scheduler_ = std::make_unique<Scheduler>(*link_, options, latest_raw_, acked_target_);
  scheduler_->start();
  return CallbackReturn::SUCCESS;
}

CM530SystemInterface::CallbackReturn CM530SystemInterface::on_deactivate(const rclcpp_lifecycle::State &)
{
  scheduler_.reset();
  if (enable_motion_ && link_ && link_->healthy()) {
    // Torque stays on: dropping it would let the arms fall.
    for (const Arm arm : kArms) {
      const std::string name{arm_name(arm)};
      if (!require_ok(link_->transact(Command::hold(arm)), "HOLD " + name)) {
        return CallbackReturn::ERROR;
      }
    }
  }
  return CallbackReturn::SUCCESS;
}

void CM530SystemInterface::release_link()
{
  scheduler_.reset();
  link_.reset();
}

CM530SystemInterface::CallbackReturn CM530SystemInterface::on_cleanup(const rclcpp_lifecycle::State &)
{
  release_link();
  return CallbackReturn::SUCCESS;
}

CM530SystemInterface::CallbackReturn CM530SystemInterface::on_shutdown(const rclcpp_lifecycle::State &)
{
  release_link();
  return CallbackReturn::SUCCESS;
}

CM530SystemInterface::CallbackReturn CM530SystemInterface::on_error(const rclcpp_lifecycle::State &)
{
  // The firmware has no STOP or watchdog. One HOLD per arm is sent only while the
  // link is still synchronized; a desynchronized link receives nothing. Motors
  // otherwise keep their last target until the hardware emergency stop.
  scheduler_.reset();
  if (enable_motion_ && link_) {
    for (const LinkResult & result : hold_arms_once(*link_)) {
      if (!result.ok()) {
        RCLCPP_ERROR(get_logger(), "HOLD after fault failed: %s", result.detail.c_str());
      }
    }
  }
  RCLCPP_ERROR(get_logger(), "CM-530 fault: communication stopped; use the hardware emergency stop if needed");
  release_link();
  return CallbackReturn::SUCCESS;
}

CM530SystemInterface::ReturnType CM530SystemInterface::read(
  const rclcpp::Time &, const rclcpp::Duration &)
{
  if (!scheduler_) {
    return ReturnType::OK;
  }
  if (scheduler_->faulted()) {
    if (!fault_logged_) {
      RCLCPP_ERROR(get_logger(), "%s", scheduler_->fault().c_str());
      fault_logged_ = true;
    }
    return ReturnType::ERROR;
  }
  ArmSamples samples;
  if (!scheduler_->snapshot(samples)) {
    return ReturnType::OK;
  }
  const auto now = std::chrono::steady_clock::now();
  for (std::size_t arm = 0; arm < kArmCount; ++arm) {
    if (now - samples[arm].stamp > feedback_stale_) {
      RCLCPP_ERROR(get_logger(), "Feedback for arm %zu is stale", arm + 1);
      return ReturnType::ERROR;
    }
    if (samples[arm].stamp == last_stamp_[arm]) {
      continue;
    }
    const double dt = std::chrono::duration<double>(samples[arm].stamp - last_stamp_[arm]).count();
    last_stamp_[arm] = samples[arm].stamp;
    for (std::size_t joint = 0; joint < kJointsPerArm; ++joint) {
      const std::size_t index = arm * kJointsPerArm + joint;
      const double position = calibration_->raw_to_rad(index, samples[arm].raw[joint]);
      set_state(position_state_[index], position);
      // The firmware reports no velocity; this is a finite difference of READ samples.
      set_state(velocity_state_[index], (position - last_rad_[index]) / dt);
      last_rad_[index] = position;
      set_state(raw_position_state_[index], static_cast<double>(samples[arm].raw[joint]));
      set_state(raw_load_state_[index], static_cast<double>(signed_load(samples[arm].load[joint])));
      set_state(
        raw_target_state_[index],
        samples[arm].acked_target ? static_cast<double>((*samples[arm].acked_target)[joint]) :
        std::numeric_limits<double>::quiet_NaN());
    }
  }
  return ReturnType::OK;
}

CM530SystemInterface::ReturnType CM530SystemInterface::write(
  const rclcpp::Time &, const rclcpp::Duration & period)
{
  if (!scheduler_ || !enable_motion_) {
    return ReturnType::OK;
  }
  const double dt = period.seconds();
  const bool have_velocity = have_last_command_ && std::isfinite(dt) && dt > 0.0;
  for (const Arm arm : kArms) {
    const auto arm_index = static_cast<std::size_t>(arm);
    RawPose target{};
    JointVelocity velocity{};
    for (std::size_t joint = 0; joint < kJointsPerArm; ++joint) {
      const std::size_t index = arm_index * kJointsPerArm + joint;
      const double command = get_command<double>(position_command_[index]);
      const auto raw = calibration_->rad_to_raw(index, command);
      if (!raw) {
        RCLCPP_ERROR(get_logger(), "Command %f rad for joint %zu is outside its calibrated limits", command, index);
        return ReturnType::ERROR;
      }
      target[joint] = *raw;
      // Counts per second from the unrounded commands, which a 1-2 count step
      // per cycle would quantize badly.
      if (have_velocity) {
        velocity[joint] = std::abs(command - last_command_[index]) / dt / kRadiansPerCount;
      }
      last_command_[index] = command;
    }
    // A busy lock only delays the target to the next control cycle.
    static_cast<void>(scheduler_->submit(arm, target, velocity));
  }
  have_last_command_ = true;
  return ReturnType::OK;
}

}  // namespace cm530_hardware

PLUGINLIB_EXPORT_CLASS(cm530_hardware::CM530SystemInterface, hardware_interface::SystemInterface)
