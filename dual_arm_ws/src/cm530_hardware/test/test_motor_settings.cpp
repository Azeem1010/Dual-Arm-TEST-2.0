#include <gtest/gtest.h>

#include <cstdlib>
#include <format>
#include <stdexcept>
#include <string>

#include "cm530_hardware/motor_settings.hpp"

using cm530_hardware::Compliance;
using cm530_hardware::kFactoryCompliance;
using cm530_hardware::kJointNames;
using cm530_hardware::MotorSettings;

namespace
{

// Every joint at the given values, except joint `special` which gets `line`.
std::string document(std::size_t special = 99, const std::string & line = "")
{
  std::string text = "schema_version: 1\njoints:\n";
  for (std::size_t index = 0; index < kJointNames.size(); ++index) {
    if (index == special) {
      if (!line.empty()) {
        text += std::format("  {}: {}\n", kJointNames[index], line);
      }
      continue;
    }
    text += std::format(
      "  {}: {{compliance_margin: {}, compliance_slope: {}, punch: {}}}\n", kJointNames[index], index, 2 << (index % 7),
      32 + index);
  }
  return text;
}

}  // namespace

TEST(MotorSettings, ReadsEveryJointInArmOrder)
{
  const auto settings = MotorSettings::from_yaml(document());
  EXPECT_EQ(settings.arms[0].margin, (std::array<std::uint16_t, 4>{0, 1, 2, 3}));
  EXPECT_EQ(settings.arms[0].slope, (std::array<std::uint16_t, 4>{2, 4, 8, 16}));
  EXPECT_EQ(settings.arms[1].slope, (std::array<std::uint16_t, 4>{32, 64, 128, 2}));
  EXPECT_EQ(settings.arms[1].punch, (std::array<std::uint16_t, 4>{36, 37, 38, 39}));
}

TEST(MotorSettings, RefusesMissingUnknownAndOutOfRange)
{
  const std::string bad[] = {
    "{compliance_margin: 1, compliance_slope: 32}",
    "{compliance_margin: 1, compliance_slope: 32, punch: 32, extra: 1}",
    "{compliance_margin: 255, compliance_slope: 32, punch: 32}",
    "{compliance_margin: -1, compliance_slope: 32, punch: 32}",
    "{compliance_margin: 1, compliance_slope: 24, punch: 32}",
    "{compliance_margin: 1, compliance_slope: 1, punch: 32}",
    "{compliance_margin: 1, compliance_slope: 256, punch: 32}",
    "{compliance_margin: 1, compliance_slope: 32, punch: 31}",
    "{compliance_margin: 1, compliance_slope: 32, punch: 1024}",
    "{compliance_margin: 1.5, compliance_slope: 32, punch: 32}",
    "{compliance_margin: ~, compliance_slope: 32, punch: 32}",
    "7",
  };
  for (const auto & line : bad) {
    EXPECT_THROW(MotorSettings::from_yaml(document(5, line)), std::runtime_error) << line;
  }
  EXPECT_THROW(MotorSettings::from_yaml(document(3)), std::runtime_error);  // joint missing
  EXPECT_THROW(
    MotorSettings::from_yaml(document() + "  arm3_arm_wrist_flex_joint: {compliance_margin: 1, compliance_slope: 32, punch: 32}\n"),
    std::runtime_error);
  EXPECT_THROW(MotorSettings::from_yaml("schema_version: 2\njoints: {}\n"), std::runtime_error);
  EXPECT_THROW(MotorSettings::from_yaml("joints: {}\n"), std::runtime_error);
  EXPECT_THROW(MotorSettings::from_file("/nonexistent/motor_settings.yaml"), std::runtime_error);
}

// The shipped prototype file starts at the factory values, so v19 first behaves like v18.
TEST(MotorSettings, ShippedPrototypeIsFactory)
{
  const char * path = std::getenv("CM530_MOTOR_SETTINGS");
  ASSERT_NE(path, nullptr);
  const auto settings = MotorSettings::from_file(path);
  EXPECT_EQ(settings.arms[0], kFactoryCompliance);
  EXPECT_EQ(settings.arms[1], kFactoryCompliance);
}
