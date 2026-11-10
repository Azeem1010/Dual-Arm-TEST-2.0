#include <gtest/gtest.h>

#include <chrono>
#include <functional>
#include <memory>
#include <optional>
#include <thread>

#include "cm530_hardware/scheduler.hpp"
#include "loop_transport.hpp"

using namespace std::chrono_literals;
using cm530_hardware::Arm;
using cm530_hardware::ArmSamples;
using cm530_hardware::Command;
using cm530_hardware::Link;
using cm530_hardware::RawPose;
using cm530_hardware::Scheduler;
using cm530_hardware::SchedulerOptions;
using cm530_test::FirmwareSim;
using cm530_test::LoopTransport;
using cm530_test::MotorFault;

namespace
{

constexpr RawPose kCenter{512, 512, 512, 512};

bool eventually(const std::function<bool()> & condition)
{
  const auto deadline = std::chrono::steady_clock::now() + 2s;
  while (std::chrono::steady_clock::now() < deadline) {
    if (condition()) {
      return true;
    }
    std::this_thread::sleep_for(1ms);
  }
  return condition();
}

}  // namespace

class SchedulerTest : public ::testing::Test
{
protected:
  void SetUp() override
  {
    sim.reset_and_boot();
    auto transport = std::make_unique<LoopTransport>(sim);
    loop = transport.get();
    link = std::make_unique<Link>(std::move(transport), 20ms);
  }

  std::unique_ptr<Scheduler> make(bool motion, int max_step = 50)
  {
    if (motion) {
      for (const Arm arm : cm530_hardware::kArms) {
        EXPECT_TRUE(link->transact(Command::ax(arm, kCenter)).ok());
        EXPECT_TRUE(link->transact(Command::torque_enable(arm, true)).ok());
      }
    }
    SchedulerOptions options;
    options.enable_motion = motion;
    options.max_step_raw = max_step;
    options.min_cycle = 1ms;
    baseline_goal_writes = sim.goal_writes();
    // In motion mode the AX above was answered OK,AX, so it is the acknowledged target.
    std::array<std::optional<RawPose>, cm530_hardware::kArmCount> acked{};
    if (motion) {
      acked = {kCenter, kCenter};
    }
    return std::make_unique<Scheduler>(*link, options, std::array{kCenter, kCenter}, acked);
  }

  std::optional<cm530_hardware::ArmSample> sample(const Scheduler & scheduler, Arm arm)
  {
    ArmSamples samples;
    if (!scheduler.snapshot(samples)) {
      return std::nullopt;
    }
    return samples[static_cast<std::size_t>(arm)];
  }

  bool sample_equals(const Scheduler & scheduler, Arm arm, const RawPose & expected)
  {
    ArmSamples samples;
    return scheduler.snapshot(samples) && samples[static_cast<std::size_t>(arm)].raw == expected;
  }

  FirmwareSim & sim{FirmwareSim::instance()};
  LoopTransport * loop{nullptr};
  std::unique_ptr<Link> link;
  int baseline_goal_writes{0};
};

TEST_F(SchedulerTest, ReadOnlyModeNeverWritesTargets)
{
  auto scheduler = make(false);
  scheduler->start();
  EXPECT_TRUE(scheduler->submit(Arm::kArm1, RawPose{520, 512, 512, 512}));
  sim.set_present(17, 400);
  ASSERT_TRUE(eventually([&] {return sample_equals(*scheduler, Arm::kArm1, RawPose{400, 512, 512, 512});}));
  scheduler->stop();
  EXPECT_EQ(sim.goal_writes(), baseline_goal_writes);
  EXPECT_EQ(sim.torque_writes(), 0);
  EXPECT_FALSE(scheduler->faulted());
}

TEST_F(SchedulerTest, SendsChangedTargetsOnceAndFollowsFeedback)
{
  auto scheduler = make(true);
  scheduler->start();
  const RawPose target{530, 500, 512, 512};
  ASSERT_TRUE(eventually([&] {return scheduler->submit(Arm::kArm1, target);}));
  ASSERT_TRUE(eventually([&] {return sample_equals(*scheduler, Arm::kArm1, target);}));
  EXPECT_EQ(sim.motor(17).goal, 530);
  EXPECT_EQ(sim.motor(3).goal, 500);
  std::this_thread::sleep_for(20ms);
  scheduler->stop();
  EXPECT_EQ(sim.goal_writes(), baseline_goal_writes + 1);
  EXPECT_FALSE(scheduler->faulted());
}

TEST_F(SchedulerTest, OversizedStepFaultsWithoutWriting)
{
  auto scheduler = make(true, 50);
  scheduler->start();
  ASSERT_TRUE(eventually([&] {return scheduler->submit(Arm::kArm2, RawPose{512, 563, 512, 512});}));
  ASSERT_TRUE(eventually([&] {return scheduler->faulted();}));
  EXPECT_NE(scheduler->fault().find("exceeds max_step_raw"), std::string::npos);
  EXPECT_EQ(sim.goal_writes(), baseline_goal_writes);
  EXPECT_EQ(sim.motor(1).goal, 512);
}

TEST_F(SchedulerTest, MotorFaultStopsAllTraffic)
{
  auto scheduler = make(true);
  sim.set_fault(8, MotorFault::kNoReply);
  scheduler->start();
  ASSERT_TRUE(eventually([&] {return scheduler->faulted();}));
  EXPECT_NE(scheduler->fault().find("DXL_TIMEOUT,arm2,8"), std::string::npos);
  const int writes = loop->writes();
  std::this_thread::sleep_for(20ms);
  EXPECT_EQ(loop->writes(), writes);
}

TEST_F(SchedulerTest, LostReplyFaultsWithoutRetry)
{
  auto scheduler = make(true);
  scheduler->start();
  loop->drop_next_reply();
  ASSERT_TRUE(eventually([&] {return scheduler->faulted();}));
  EXPECT_FALSE(link->healthy());
  const int writes = loop->writes();
  std::this_thread::sleep_for(40ms);
  EXPECT_EQ(loop->writes(), writes);
}

TEST_F(SchedulerTest, StopJoinsPromptlyAndIsRepeatable)
{
  auto scheduler = make(false);
  scheduler->start();
  const auto started = std::chrono::steady_clock::now();
  scheduler->stop();
  scheduler->stop();
  EXPECT_LT(std::chrono::steady_clock::now() - started, 500ms);
}

TEST_F(SchedulerTest, ReadOnlyModeReportsNoAcknowledgedTarget)
{
  auto scheduler = make(false);
  scheduler->start();
  EXPECT_TRUE(scheduler->submit(Arm::kArm2, RawPose{520, 512, 512, 512}));
  sim.set_present(12, 431);
  ASSERT_TRUE(eventually([&] {return sample_equals(*scheduler, Arm::kArm2, RawPose{431, 512, 512, 512});}));
  scheduler->stop();
  for (const Arm arm : cm530_hardware::kArms) {
    const auto current = sample(*scheduler, arm);
    ASSERT_TRUE(current);
    EXPECT_FALSE(current->acked_target);
  }
}

TEST_F(SchedulerTest, AcknowledgedTargetFollowsOkAx)
{
  auto scheduler = make(true);
  ASSERT_TRUE(sample(*scheduler, Arm::kArm1)->acked_target == kCenter);
  scheduler->start();
  const RawPose target{530, 500, 512, 512};
  ASSERT_TRUE(eventually([&] {return scheduler->submit(Arm::kArm1, target);}));
  ASSERT_TRUE(eventually([&] {
      const auto current = sample(*scheduler, Arm::kArm1);
      return current && current->acked_target == target;
    }));
  scheduler->stop();
  EXPECT_TRUE(sample(*scheduler, Arm::kArm2)->acked_target == kCenter);
}

TEST_F(SchedulerTest, RefusedTargetIsNeverReportedAsAcknowledged)
{
  auto scheduler = make(true, 50);
  scheduler->start();
  ASSERT_TRUE(eventually([&] {return scheduler->submit(Arm::kArm2, RawPose{512, 563, 512, 512});}));
  ASSERT_TRUE(eventually([&] {return scheduler->faulted();}));
  scheduler->stop();
  EXPECT_TRUE(sample(*scheduler, Arm::kArm2)->acked_target == kCenter);
}
