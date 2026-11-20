#include <gtest/gtest.h>

#include "cm530_hardware/protocol.hpp"

using cm530_hardware::Arm;
using cm530_hardware::Command;
using cm530_hardware::Compliance;
using cm530_hardware::RawLoad;
using cm530_hardware::RawPose;
using cm530_hardware::RawSpeed;
using cm530_hardware::ReplyStatus;
using cm530_hardware::classify_reply;
using cm530_hardware::format_command;

namespace
{
const RawPose kPose{90, 567, 712, 825};
}

TEST(Protocol, FormatsExactBytes)
{
  EXPECT_EQ(format_command(Command::ping()), "PING\n");
  EXPECT_EQ(format_command(Command::version()), "VERSION\n");
  EXPECT_EQ(format_command(Command::get_home(Arm::kArm2)), "GET_HOME,arm2\n");
  EXPECT_EQ(format_command(Command::read(Arm::kArm1)), "READ,arm1\n");
  EXPECT_EQ(format_command(Command::hold(Arm::kArm2)), "HOLD,arm2\n");
  EXPECT_EQ(format_command(Command::ax(Arm::kArm1, kPose)), "AX,arm1,90,567,712,825\n");
  EXPECT_EQ(
    format_command(Command::ax(Arm::kArm2, kPose, RawSpeed{1, 87, 300, 1023})),
    "AX,arm2,90,567,712,825,1,87,300,1023\n");
  EXPECT_EQ(format_command(Command::torque_enable(Arm::kArm2, true)), "TORQUE,arm2,1\n");
  EXPECT_EQ(format_command(Command::torque_enable(Arm::kArm1, false)), "TORQUE,arm1,0\n");
  EXPECT_EQ(
    format_command(Command::set_compliance(Arm::kArm2, Compliance{{0, 1, 2, 254}, {2, 16, 32, 128}, {32, 64, 512, 1023}})),
    "COMP,arm2,0,1,2,254,2,16,32,128,32,64,512,1023\n");
  EXPECT_EQ(format_command(Command::get_compliance(Arm::kArm1)), "GET_COMP,arm1\n");
  EXPECT_EQ(format_command(Command::diag(Arm::kArm2)), "DIAG,arm2\n");
}

TEST(Protocol, AcceptsExactReplies)
{
  EXPECT_EQ(classify_reply(Command::ping(), "PONG").status, ReplyStatus::kOk);
  EXPECT_EQ(classify_reply(Command::version(), "VERSION,7").status, ReplyStatus::kOk);
  EXPECT_EQ(classify_reply(Command::ax(Arm::kArm1, kPose), "OK,AX,arm1").status, ReplyStatus::kOk);
  EXPECT_EQ(classify_reply(Command::hold(Arm::kArm2), "OK,HOLD,arm2").status, ReplyStatus::kOk);
  EXPECT_EQ(classify_reply(Command::torque_enable(Arm::kArm1, true), "OK,TORQUE,arm1,1").status, ReplyStatus::kOk);
  const auto read = classify_reply(Command::read(Arm::kArm2), "POS,arm2,1,2,3,1023,0,1023,1024,2047");
  ASSERT_EQ(read.status, ReplyStatus::kOk);
  EXPECT_EQ(read.pose, (RawPose{1, 2, 3, 1023}));
  EXPECT_EQ(read.load, (RawLoad{0, 1023, 1024, 2047}));
  EXPECT_EQ(classify_reply(Command::set_compliance(Arm::kArm1, {}), "OK,COMP,arm1").status, ReplyStatus::kOk);
  const auto comp = classify_reply(Command::get_compliance(Arm::kArm1), "COMP,arm1,0,1,2,254,2,16,32,128,32,64,512,1023");
  ASSERT_EQ(comp.status, ReplyStatus::kOk);
  EXPECT_EQ(comp.compliance, (Compliance{{0, 1, 2, 254}, {2, 16, 32, 128}, {32, 64, 512, 1023}}));
  const auto diag = classify_reply(Command::diag(Arm::kArm2), "DIAG,arm2,120,121,122,123,30,31,32,255");
  ASSERT_EQ(diag.status, ReplyStatus::kOk);
  EXPECT_EQ(diag.diagnostics->voltage, (std::array<std::uint16_t, 4>{120, 121, 122, 123}));
  EXPECT_EQ(diag.diagnostics->temperature, (std::array<std::uint16_t, 4>{30, 31, 32, 255}));
  const auto home = classify_reply(Command::get_home(Arm::kArm1), "HOME,arm1,90,567,712,825");
  ASSERT_EQ(home.status, ReplyStatus::kOk);
  EXPECT_EQ(home.pose, kPose);
}

TEST(Protocol, RejectsAnythingElse)
{
  const auto ax = Command::ax(Arm::kArm1, kPose);
  for (const char * line : {"OK,AX,arm2", "OK,AX", "OK,AX,arm1,extra", "OK", "ok,ax,arm1", "PONG", ""}) {
    EXPECT_EQ(classify_reply(ax, line).status, ReplyStatus::kMismatch) << line;
  }
  EXPECT_EQ(classify_reply(Command::version(), "VERSION,4").status, ReplyStatus::kMismatch);
  // A v17 board (protocol 5) must be refused: it would ignore Moving Speed.
  EXPECT_EQ(classify_reply(Command::version(), "VERSION,5").status, ReplyStatus::kMismatch);
  // A v18 board (protocol 6) must be refused: its READ has no load and it has no COMP.
  EXPECT_EQ(classify_reply(Command::version(), "VERSION,6").status, ReplyStatus::kMismatch);
  EXPECT_EQ(classify_reply(Command::torque_enable(Arm::kArm1, true), "OK,TORQUE,arm1,0").status, ReplyStatus::kMismatch);
  const auto read = Command::read(Arm::kArm1);
  for (const char * line : {
      "POS,arm2,1,2,3,4,0,0,0,0", "HOME,arm1,1,2,3,4,0,0,0,0", "POS,arm1,1,2,3,4", "POS,arm1,1,2,3,4,0,0,0",
      "POS,arm1,1,2,3,4,0,0,0,0,0", "POS,arm1,1024,2,3,4,0,0,0,0", "POS,arm1,1,2,3,4,0,0,0,2048",
      "POS,arm1,-1,2,3,4,0,0,0,0", "POS,arm1,+1,2,3,4,0,0,0,0", "POS,arm1,1.5,2,3,4,0,0,0,0",
      "POS,arm1,,2,3,4,0,0,0,0", "POS,arm1,1x,2,3,4,0,0,0,0", "POS,arm1,1,2,3,4,0,0,0,-1", "OK,READ,arm1"})
  {
    EXPECT_EQ(classify_reply(read, line).status, ReplyStatus::kMismatch) << line;
  }
  EXPECT_EQ(classify_reply(Command::get_home(Arm::kArm1), "HOME,arm1,1,2,3,4,0,0,0,0").status, ReplyStatus::kMismatch);
  const auto get = Command::get_compliance(Arm::kArm1);
  for (const char * line : {
      "COMP,arm1,1,1,1,1,32,32,32,32,32,32,32", "COMP,arm2,1,1,1,1,32,32,32,32,32,32,32,32",
      "COMP,arm1,255,1,1,1,32,32,32,32,32,32,32,32", "COMP,arm1,1,1,1,1,256,32,32,32,32,32,32,32",
      "COMP,arm1,1,1,1,1,32,32,32,32,32,32,32,1024", "OK,COMP,arm1"})
  {
    EXPECT_EQ(classify_reply(get, line).status, ReplyStatus::kMismatch) << line;
  }
  EXPECT_EQ(classify_reply(Command::set_compliance(Arm::kArm1, {}), "OK,COMP,arm2").status, ReplyStatus::kMismatch);
  for (const char * line : {"DIAG,arm1,1,2,3,4,5,6,7", "DIAG,arm1,1,2,3,4,5,6,7,256", "DIAG,arm2,1,2,3,4,5,6,7,8"}) {
    EXPECT_EQ(classify_reply(Command::diag(Arm::kArm1), line).status, ReplyStatus::kMismatch) << line;
  }
}

TEST(Protocol, SeparatesErrorsAndRestarts)
{
  const auto read = Command::read(Arm::kArm1);
  EXPECT_EQ(classify_reply(read, "ERR,DXL_TIMEOUT,arm1,3").status, ReplyStatus::kDeviceError);
  EXPECT_EQ(classify_reply(read, "READY,7").status, ReplyStatus::kRestarted);
  EXPECT_EQ(classify_reply(read, "READY").status, ReplyStatus::kRestarted);
}
