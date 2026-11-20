#pragma once

#include <array>
#include <string>

#include "cm530_hardware/protocol.hpp"

namespace cm530_hardware
{

// Compliance Margin/Slope and Punch for every joint (firmware v19 COMP), from a
// YAML file:
//
//   schema_version: 1
//   joints:
//     arm1_arm_shoulder_pan_joint: {compliance_margin: 1, compliance_slope: 32, punch: 32}
//     ... all eight joints ...
//
// These are tuning values, not calibration. Loading throws std::runtime_error
// when a joint or key is missing, unknown or outside the firmware's range, so a
// typo can never silently leave a motor at another value.
struct MotorSettings
{
  std::array<Compliance, kArmCount> arms{};

  static MotorSettings from_yaml(const std::string & text);
  static MotorSettings from_file(const std::string & path);
};

}  // namespace cm530_hardware
