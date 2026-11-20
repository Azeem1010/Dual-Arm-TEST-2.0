#pragma once

// CM-530 firmware v19 / serial protocol 7, per ROS_CM530_INTERFACE_SPEC.md. v18
// added four AX-12A Moving Speeds (1..1023) to AX; v19 adds Present Load to READ
// and the COMP, GET_COMP and DIAG commands. Older protocols are refused.
// The firmware HOME and LED commands are deliberately not exposed: HOME jumps
// straight to a preset with no interpolation.

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace cm530_hardware
{

inline constexpr int kProtocolVersion = 7;
inline constexpr std::size_t kArmCount = 2;
inline constexpr std::size_t kJointsPerArm = 4;
inline constexpr std::size_t kJointCount = kArmCount * kJointsPerArm;
inline constexpr int kMaxRaw = 1023;
// AX-12A Moving Speed register range. 0 means maximum speed without speed
// control, so the firmware refuses it and the driver never sends it.
inline constexpr int kMinSpeed = 1;
inline constexpr int kMaxSpeed = 1023;
// AX-12A Present Load: 0..1023 is the magnitude, bit 10 (1024) marks the CW direction.
inline constexpr int kMaxLoad = 2047;
// Compliance and Punch limits the firmware accepts (v19 COMP).
inline constexpr int kMaxComplianceMargin = 254;
inline constexpr int kMinPunch = 32;
inline constexpr int kMaxPunch = 1023;

enum class Arm : std::uint8_t { kArm1 = 0, kArm2 = 1 };
inline constexpr std::array<Arm, kArmCount> kArms{Arm::kArm1, Arm::kArm2};

using RawPose = std::array<std::uint16_t, kJointsPerArm>;
// AX-12A Moving Speed per joint, about 0.111 rpm per unit.
using RawSpeed = std::array<std::uint16_t, kJointsPerArm>;
// AX-12A Present Load register per joint, 0..2047 as the firmware reported it.
using RawLoad = std::array<std::uint16_t, kJointsPerArm>;

// Signed load: CCW positive, CW negative, magnitude 0..1023 (about 0.1 % of the
// maximum torque per unit). Not calibrated against any torque measurement.
int signed_load(std::uint16_t raw) noexcept;

// Compliance Margin and Slope (CW and CCW alike) and Punch per joint. These are
// AX-12A RAM registers: the factory values return at every motor power-up.
struct Compliance
{
  std::array<std::uint16_t, kJointsPerArm> margin{};
  std::array<std::uint16_t, kJointsPerArm> slope{};
  std::array<std::uint16_t, kJointsPerArm> punch{};

  bool operator==(const Compliance &) const = default;
};

// AX-12A factory values: margin 1, slope 32, punch 32.
inline constexpr Compliance kFactoryCompliance{{1, 1, 1, 1}, {32, 32, 32, 32}, {32, 32, 32, 32}};

// Slope is one of the seven AX-12A steps 2, 4, ..., 128.
bool valid_slope(int value) noexcept;

// Present Voltage (0.1 V) and Present Temperature (deg C) per joint.
struct Diagnostics
{
  std::array<std::uint16_t, kJointsPerArm> voltage{};
  std::array<std::uint16_t, kJointsPerArm> temperature{};
};

// Motor IDs by arm and joint, matching APP/src/ax12.c.
inline constexpr std::array<std::array<int, kJointsPerArm>, kArmCount> kMotorIds{{
  {17, 3, 2, 15},
  {12, 1, 8, 16},
}};

inline constexpr std::array<std::string_view, kJointCount> kJointNames{
  "arm1_arm_shoulder_pan_joint", "arm1_arm_shoulder_lift_joint",
  "arm1_arm_elbow_flex_joint", "arm1_arm_wrist_flex_joint",
  "arm2_arm_shoulder_pan_joint", "arm2_arm_shoulder_lift_joint",
  "arm2_arm_elbow_flex_joint", "arm2_arm_wrist_flex_joint",
};

std::string_view arm_name(Arm arm) noexcept;

enum class CommandKind { kPing, kVersion, kGetHome, kRead, kHold, kAx, kTorque, kSetCompliance, kGetCompliance, kDiag };

struct Command
{
  CommandKind kind{CommandKind::kPing};
  Arm arm{Arm::kArm1};
  RawPose pose{};
  bool torque{false};
  // AX only: without speeds the firmware uses its default Moving Speed.
  std::optional<RawSpeed> speed{};
  // COMP only.
  Compliance compliance{};

  static Command ping() { return make(CommandKind::kPing, Arm::kArm1); }
  static Command version() { return make(CommandKind::kVersion, Arm::kArm1); }
  static Command get_home(Arm arm) { return make(CommandKind::kGetHome, arm); }
  static Command read(Arm arm) { return make(CommandKind::kRead, arm); }
  static Command hold(Arm arm) { return make(CommandKind::kHold, arm); }
  static Command ax(Arm arm, const RawPose & pose)
  {
    Command command = make(CommandKind::kAx, arm);
    command.pose = pose;
    return command;
  }
  static Command ax(Arm arm, const RawPose & pose, const RawSpeed & speed)
  {
    Command command = ax(arm, pose);
    command.speed = speed;
    return command;
  }
  static Command torque_enable(Arm arm, bool enable)
  {
    Command command = make(CommandKind::kTorque, arm);
    command.torque = enable;
    return command;
  }
  static Command set_compliance(Arm arm, const Compliance & compliance)
  {
    Command command = make(CommandKind::kSetCompliance, arm);
    command.compliance = compliance;
    return command;
  }
  static Command get_compliance(Arm arm) { return make(CommandKind::kGetCompliance, arm); }
  static Command diag(Arm arm) { return make(CommandKind::kDiag, arm); }

private:
  static Command make(CommandKind kind, Arm arm)
  {
    Command command;
    command.kind = kind;
    command.arm = arm;
    return command;
  }
};

// Serialized command including its LF terminator.
std::string format_command(const Command & command);

enum class ReplyStatus { kOk, kDeviceError, kRestarted, kMismatch };

struct Reply
{
  ReplyStatus status{ReplyStatus::kMismatch};
  std::optional<RawPose> pose{};                 // READ, GET_HOME
  std::optional<RawLoad> load{};                 // READ
  std::optional<Compliance> compliance{};        // GET_COMP
  std::optional<Diagnostics> diagnostics{};      // DIAG
};

// Strictly matches one complete line (without EOL) to the command it answers.
Reply classify_reply(const Command & command, std::string_view line);

}  // namespace cm530_hardware
