#include "cm530_hardware/motor_settings.hpp"

#include <yaml-cpp/yaml.h>

#include <format>
#include <set>
#include <stdexcept>

namespace cm530_hardware
{
namespace
{

int require_int(const YAML::Node & node, const std::string & key, const std::string & joint, int min, int max)
{
  const YAML::Node value = node[key];
  if (!value.IsDefined() || value.IsNull() || !value.IsScalar()) {
    throw std::runtime_error(std::format("{}.{} is missing", joint, key));
  }
  int number = 0;
  try {
    number = value.as<int>();
  } catch (const YAML::Exception &) {
    throw std::runtime_error(std::format("{}.{} must be an integer", joint, key));
  }
  if (number < min || number > max) {
    throw std::runtime_error(std::format("{}.{}={} is outside {}..{}", joint, key, number, min, max));
  }
  return number;
}

}  // namespace

MotorSettings MotorSettings::from_yaml(const std::string & text)
{
  const YAML::Node root = YAML::Load(text);
  if (!root.IsMap()) {
    throw std::runtime_error("motor settings must be a YAML map");
  }
  const YAML::Node version = root["schema_version"];
  if (!version.IsDefined() || version.as<int>() != 1) {
    throw std::runtime_error("motor settings schema_version must be 1");
  }
  const YAML::Node joints = root["joints"];
  if (!joints.IsDefined() || !joints.IsMap()) {
    throw std::runtime_error("motor settings need a joints map");
  }
  const std::set<std::string> keys{"compliance_margin", "compliance_slope", "punch"};
  std::set<std::string> known;
  for (const std::string_view name : kJointNames) {
    known.emplace(name);
  }
  for (const auto & entry : joints) {
    const auto name = entry.first.as<std::string>();
    if (!known.contains(name)) {
      throw std::runtime_error(std::format("motor settings name an unknown joint {}", name));
    }
    if (!entry.second.IsMap()) {
      throw std::runtime_error(std::format("{} must be a map", name));
    }
    for (const auto & field : entry.second) {
      if (!keys.contains(field.first.as<std::string>())) {
        throw std::runtime_error(std::format("{} has an unknown key {}", name, field.first.as<std::string>()));
      }
    }
  }
  MotorSettings settings;
  for (std::size_t index = 0; index < kJointCount; ++index) {
    const std::string name{kJointNames[index]};
    const YAML::Node node = joints[name];
    if (!node.IsDefined()) {
      throw std::runtime_error(std::format("motor settings miss joint {}", name));
    }
    Compliance & arm = settings.arms[index / kJointsPerArm];
    const std::size_t joint = index % kJointsPerArm;
    arm.margin[joint] = static_cast<std::uint16_t>(
      require_int(node, "compliance_margin", name, 0, kMaxComplianceMargin));
    const int slope = require_int(node, "compliance_slope", name, 2, 128);
    if (!valid_slope(slope)) {
      throw std::runtime_error(std::format("{}.compliance_slope={} must be 2, 4, 8, 16, 32, 64 or 128", name, slope));
    }
    arm.slope[joint] = static_cast<std::uint16_t>(slope);
    arm.punch[joint] = static_cast<std::uint16_t>(require_int(node, "punch", name, kMinPunch, kMaxPunch));
  }
  return settings;
}

MotorSettings MotorSettings::from_file(const std::string & path)
{
  YAML::Node probe;
  try {
    probe = YAML::LoadFile(path);
  } catch (const YAML::Exception & error) {
    throw std::runtime_error(std::format("cannot read motor settings {}: {}", path, error.what()));
  }
  return from_yaml(YAML::Dump(probe));
}

}  // namespace cm530_hardware
