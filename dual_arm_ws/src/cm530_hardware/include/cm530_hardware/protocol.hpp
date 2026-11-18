#pragma once

// CM-530 firmware v18 / serial protocol 6, per ROS_CM530_INTERFACE_SPEC.md. v18
// adds four AX-12A Moving Speeds (1..1023) to AX; v17 (protocol 5) is refused.
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

inline constexpr std::size_t kArmCount = 2;
inline constexpr std::size_t kJointsPerArm = 4;
inline constexpr std::size_t kJointCount = kArmCount * kJointsPerArm;
inline constexpr int kMaxRaw = 1023;
// AX-12A Moving Speed register range. 0 means maximum speed without speed
// control, so the firmware refuses it and the driver never sends it.
inline constexpr int kMinSpeed = 1;
inline constexpr int kMaxSpeed = 1023;

enum class Arm : std::uint8_t { kArm1 = 0, kArm2 = 1 };
inline constexpr std::array<Arm, kArmCount> kArms{Arm::kArm1, Arm::kArm2};

using RawPose = std::array<std::uint16_t, kJointsPerArm>;
// AX-12A Moving Speed per joint, about 0.111 rpm per unit.
using RawSpeed = std::array<std::uint16_t, kJointsPerArm>;

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

enum class CommandKind { kPing, kVersion, kGetHome, kRead, kHold, kAx, kTorque };

struct Command
{
  CommandKind kind{CommandKind::kPing};
  Arm arm{Arm::kArm1};
  RawPose pose{};
  bool torque{false};
  // AX only: without speeds the firmware uses its default Moving Speed.
  std::optional<RawSpeed> speed{};

  static Command ping() { return {CommandKind::kPing, Arm::kArm1, {}, false, {}}; }
  static Command version() { return {CommandKind::kVersion, Arm::kArm1, {}, false, {}}; }
  static Command get_home(Arm arm) { return {CommandKind::kGetHome, arm, {}, false, {}}; }
  static Command read(Arm arm) { return {CommandKind::kRead, arm, {}, false, {}}; }
  static Command hold(Arm arm) { return {CommandKind::kHold, arm, {}, false, {}}; }
  static Command ax(Arm arm, const RawPose & pose) { return {CommandKind::kAx, arm, pose, false, {}}; }
  static Command ax(Arm arm, const RawPose & pose, const RawSpeed & speed)
  {
    return {CommandKind::kAx, arm, pose, false, speed};
  }
  static Command torque_enable(Arm arm, bool enable) { return {CommandKind::kTorque, arm, {}, enable, {}}; }
};

// Serialized command including its LF terminator.
std::string format_command(const Command & command);

enum class ReplyStatus { kOk, kDeviceError, kRestarted, kMismatch };

struct Reply
{
  ReplyStatus status{ReplyStatus::kMismatch};
  std::optional<RawPose> pose{};
};

// Strictly matches one complete line (without EOL) to the command it answers.
Reply classify_reply(const Command & command, std::string_view line);

}  // namespace cm530_hardware
