// Every test here talks to the real v19 parser and AX-12 driver code.

#include <gtest/gtest.h>

#include <chrono>
#include <memory>

#include "cm530_hardware/link.hpp"
#include "loop_transport.hpp"

using namespace std::chrono_literals;
using cm530_hardware::Arm;
using cm530_hardware::Command;
using cm530_hardware::Compliance;
using cm530_hardware::kFactoryCompliance;
using cm530_hardware::Link;
using cm530_hardware::LinkStatus;
using cm530_hardware::RawLoad;
using cm530_hardware::RawPose;
using cm530_test::FirmwareSim;
using cm530_test::LoopTransport;
using cm530_test::MotorFault;

class LinkTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    boot_output = sim.reset_and_boot();
    auto transport = std::make_unique<LoopTransport>(sim);
    loop = transport.get();
    link = std::make_unique<Link>(std::move(transport), 20ms);
  }

  FirmwareSim & sim{FirmwareSim::instance()};
  LoopTransport * loop{nullptr};
  std::unique_ptr<Link> link;
  std::string boot_output;
};

TEST_F(LinkTest, BootsWithTorqueOffAndReady)
{
  EXPECT_EQ(boot_output, "READY,7\r\n");
  EXPECT_FALSE(sim.motor(17).torque);
}

TEST_F(LinkTest, HandshakesWithOrWithoutReady)
{
  loop->inject(boot_output);
  EXPECT_TRUE(link->handshake(20ms).ok());
  EXPECT_TRUE(link->handshake(2ms).ok());
}

TEST_F(LinkTest, HandshakeClearsPartialLineLeftInFirmware)
{
  sim.feed("VERSI");
  EXPECT_TRUE(link->handshake(2ms).ok());
  EXPECT_TRUE(link->healthy());
}

TEST_F(LinkTest, HandshakeNeverExecutesACommandLeftInFirmware)
{
  const int goals = sim.goal_writes();
  sim.feed("HOME,arm1");
  EXPECT_TRUE(link->handshake(2ms).ok());
  EXPECT_EQ(sim.goal_writes(), goals);
}

TEST_F(LinkTest, HoldAfterFaultCoversBothArms)
{
  const int goals = sim.goal_writes();
  const auto results = cm530_hardware::hold_arms_once(*link);
  ASSERT_EQ(results.size(), 2U);
  EXPECT_TRUE(results[0].ok());
  EXPECT_TRUE(results[1].ok());
  EXPECT_EQ(sim.goal_writes(), goals + 2);
}

TEST_F(LinkTest, HoldAfterFaultIsNotRetriedAndStillTriesTheOtherArm)
{
  sim.set_fault(17, MotorFault::kNoReply);
  const int writes = loop->writes();
  const auto results = cm530_hardware::hold_arms_once(*link);
  ASSERT_EQ(results.size(), 2U);
  EXPECT_EQ(results[0].status, LinkStatus::kDeviceError);
  EXPECT_TRUE(results[1].ok());
  EXPECT_EQ(loop->writes(), writes + 2);
}

TEST_F(LinkTest, HoldIsNeverSentOnADesynchronizedLink)
{
  loop->drop_next_reply();
  EXPECT_FALSE(link->transact(Command::read(Arm::kArm1)).ok());
  ASSERT_FALSE(link->healthy());
  const int writes = loop->writes();
  EXPECT_TRUE(cm530_hardware::hold_arms_once(*link).empty());
  EXPECT_EQ(loop->writes(), writes);
}

TEST_F(LinkTest, RejectsInitFailureAtHandshake)
{
  loop->inject("ERR,INIT_FAILED\r\n");
  EXPECT_FALSE(link->handshake(20ms).ok());
  EXPECT_FALSE(link->healthy());
}

TEST_F(LinkTest, ReadsFirmwareHomePresets)
{
  const auto arm1 = link->transact(Command::get_home(Arm::kArm1));
  ASSERT_TRUE(arm1.ok());
  EXPECT_EQ(arm1.pose, (RawPose{256, 512, 512, 512}));
  const auto arm2 = link->transact(Command::get_home(Arm::kArm2));
  ASSERT_TRUE(arm2.ok());
  EXPECT_EQ(arm2.pose, (RawPose{256, 512, 512, 512}));
  EXPECT_EQ(sim.goal_writes(), 0);
}

TEST_F(LinkTest, MapsJointOrderToMotorIds)
{
  ASSERT_TRUE(link->transact(Command::ax(Arm::kArm2, RawPose{100, 200, 300, 400})).ok());
  EXPECT_EQ(sim.motor(12).goal, 100);
  EXPECT_EQ(sim.motor(1).goal, 200);
  EXPECT_EQ(sim.motor(8).goal, 300);
  EXPECT_EQ(sim.motor(16).goal, 400);
  EXPECT_EQ(sim.motor(17).goal, 512);

  sim.set_present(17, 11);
  sim.set_present(3, 22);
  sim.set_present(2, 33);
  sim.set_present(15, 44);
  const auto read = link->transact(Command::read(Arm::kArm1));
  ASSERT_TRUE(read.ok());
  EXPECT_EQ(read.pose, (RawPose{11, 22, 33, 44}));
}

TEST_F(LinkTest, FirmwareRequiresTargetBeforeTorque)
{
  const auto refused = link->transact(Command::torque_enable(Arm::kArm1, true));
  EXPECT_EQ(refused.status, LinkStatus::kDeviceError);
  EXPECT_EQ(refused.detail, "ERR,NO_TARGET,arm1");
  EXPECT_TRUE(link->healthy());
  EXPECT_FALSE(sim.motor(17).torque);

  ASSERT_TRUE(link->transact(Command::ax(Arm::kArm1, RawPose{512, 512, 512, 512})).ok());
  ASSERT_TRUE(link->transact(Command::torque_enable(Arm::kArm1, true)).ok());
  EXPECT_TRUE(sim.motor(17).torque);
  EXPECT_FALSE(sim.motor(12).torque);
}

TEST_F(LinkTest, ReportsMotorFaultsWithoutPartialPose)
{
  sim.set_fault(3, MotorFault::kNoReply);
  const auto timeout = link->transact(Command::read(Arm::kArm1));
  EXPECT_EQ(timeout.status, LinkStatus::kDeviceError);
  EXPECT_EQ(timeout.detail, "ERR,DXL_TIMEOUT,arm1,3");
  EXPECT_FALSE(timeout.pose);
  EXPECT_TRUE(link->healthy());

  sim.set_fault(3, MotorFault::kNone);
  sim.set_fault(15, MotorFault::kOverheat);
  const auto overheat = link->transact(Command::read(Arm::kArm1));
  EXPECT_EQ(overheat.detail, "ERR,DXL_MOTOR,arm1,15,4");
  EXPECT_TRUE(link->transact(Command::read(Arm::kArm2)).ok());
}

TEST_F(LinkTest, TimeoutLatchesAndNeverResends)
{
  loop->drop_next_reply();
  EXPECT_EQ(link->transact(Command::ax(Arm::kArm1, RawPose{1, 2, 3, 4})).status, LinkStatus::kTimeout);
  EXPECT_FALSE(link->healthy());
  const int writes = loop->writes();
  EXPECT_EQ(link->transact(Command::read(Arm::kArm1)).status, LinkStatus::kDown);
  EXPECT_EQ(loop->writes(), writes);
}

TEST_F(LinkTest, WrongOrRestartRepliesLatch)
{
  loop->override_next_reply("OK,AX,arm2\r\n");
  EXPECT_EQ(link->transact(Command::ax(Arm::kArm1, RawPose{1, 2, 3, 4})).status, LinkStatus::kMismatch);
  EXPECT_FALSE(link->healthy());

  SetUp();
  loop->override_next_reply("READY,7\r\n");
  EXPECT_EQ(link->transact(Command::read(Arm::kArm1)).status, LinkStatus::kRestarted);
  EXPECT_FALSE(link->healthy());

  SetUp();
  loop->override_next_reply("ERR,OVERFLOW\r\n");
  EXPECT_EQ(link->transact(Command::read(Arm::kArm1)).status, LinkStatus::kDeviceError);
  EXPECT_FALSE(link->healthy());
}

TEST_F(LinkTest, StaleInputBlocksTheNextRequest)
{
  loop->inject("OK,AX,arm1\r\n");
  const int writes = loop->writes();
  EXPECT_EQ(link->transact(Command::read(Arm::kArm1)).status, LinkStatus::kMismatch);
  EXPECT_EQ(loop->writes(), writes);
}

TEST_F(LinkTest, ToleratesLeftoverLineEndingsAndFragments)
{
  loop->inject("\n");
  loop->set_chunk(1);
  const auto read = link->transact(Command::read(Arm::kArm1));
  ASSERT_TRUE(read.ok());
  EXPECT_EQ(read.pose, (RawPose{512, 512, 512, 512}));
  EXPECT_TRUE(link->transact(Command::ping()).ok());
}

TEST_F(LinkTest, ReadCarriesPresentLoad)
{
  sim.set_load(17, 0);
  sim.set_load(3, 1023);
  sim.set_load(2, 1024 + 57);
  sim.set_load(15, 2047);
  const auto read = link->transact(Command::read(Arm::kArm1));
  ASSERT_TRUE(read.ok());
  EXPECT_EQ(read.load, (RawLoad{0, 1023, 1081, 2047}));
  EXPECT_EQ(cm530_hardware::signed_load(1081), -57);
  EXPECT_EQ(cm530_hardware::signed_load(1023), 1023);
}

TEST_F(LinkTest, ComplianceWritesAndReadsBack)
{
  const auto factory = link->transact(Command::get_compliance(Arm::kArm2));
  ASSERT_TRUE(factory.ok());
  EXPECT_EQ(factory.compliance, kFactoryCompliance);

  const Compliance wanted{{0, 1, 2, 254}, {2, 16, 32, 128}, {32, 64, 512, 1023}};
  const int goals = sim.goal_writes();
  ASSERT_TRUE(link->transact(Command::set_compliance(Arm::kArm2, wanted)).ok());
  EXPECT_EQ(sim.compliance_writes(), 2);
  EXPECT_EQ(sim.goal_writes(), goals);  // no target, no motion
  EXPECT_FALSE(sim.motor(12).torque);
  EXPECT_EQ(sim.motor(1).slope_cw, 16);
  EXPECT_EQ(sim.motor(1).slope_ccw, 16);
  EXPECT_EQ(sim.motor(16).punch, 1023);
  const auto check = link->transact(Command::get_compliance(Arm::kArm2));
  ASSERT_TRUE(check.ok());
  EXPECT_EQ(check.compliance, wanted);
  EXPECT_EQ(link->transact(Command::get_compliance(Arm::kArm1)).compliance, kFactoryCompliance);
}

TEST_F(LinkTest, ComplianceOutOfRangeIsRefusedByTheFirmware)
{
  Compliance bad = kFactoryCompliance;
  bad.slope[2] = 24;
  const auto refused = link->transact(Command::set_compliance(Arm::kArm1, bad));
  EXPECT_EQ(refused.status, LinkStatus::kDeviceError);
  EXPECT_EQ(refused.detail, "ERR,RANGE,arm1");
  EXPECT_EQ(sim.compliance_writes(), 0);
  EXPECT_TRUE(link->healthy());
}

TEST_F(LinkTest, AsymmetricComplianceIsReportedNotHidden)
{
  sim.set_slope_cw(2, 64);
  const auto read = link->transact(Command::get_compliance(Arm::kArm1));
  EXPECT_EQ(read.status, LinkStatus::kDeviceError);
  EXPECT_EQ(read.detail, "ERR,DXL_ASYM,arm1,2");
  EXPECT_FALSE(read.compliance);
}

TEST_F(LinkTest, DiagReadsVoltageAndTemperature)
{
  const auto diag = link->transact(Command::diag(Arm::kArm1));
  ASSERT_TRUE(diag.ok());
  ASSERT_TRUE(diag.diagnostics);
  EXPECT_EQ(diag.diagnostics->voltage, (std::array<std::uint16_t, 4>{120, 120, 120, 120}));
  EXPECT_EQ(diag.diagnostics->temperature, (std::array<std::uint16_t, 4>{30, 30, 30, 30}));
}

TEST_F(LinkTest, OlderProtocolIsRefusedAtHandshake)
{
  loop->override_next_reply("VERSION,6\r\n");
  EXPECT_EQ(link->handshake(2ms).status, LinkStatus::kMismatch);
  EXPECT_FALSE(link->healthy());

  SetUp();
  loop->inject("READY,6\r\n");
  EXPECT_EQ(link->handshake(20ms).status, LinkStatus::kMismatch);
}

TEST_F(LinkTest, TransportFailureLatches)
{
  loop->fail_io();
  EXPECT_EQ(link->transact(Command::ping()).status, LinkStatus::kIoError);
  EXPECT_FALSE(link->healthy());
}
