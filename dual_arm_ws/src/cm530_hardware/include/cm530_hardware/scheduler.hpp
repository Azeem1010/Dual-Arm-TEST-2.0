#pragma once

#include <array>
#include <atomic>
#include <chrono>
#include <mutex>
#include <optional>
#include <string>
#include <thread>

#include "cm530_hardware/link.hpp"
#include "cm530_hardware/protocol.hpp"

namespace cm530_hardware
{

struct ArmSample
{
  // Present Position exactly as the last successful READ returned it.
  RawPose raw{};
  std::chrono::steady_clock::time_point stamp{};
  // The last AX the firmware answered OK,AX to; empty until one is acknowledged.
  // OK,AX echoes nothing, so the host keeps the values it sent (spec 4.2).
  std::optional<RawPose> acked_target{};
};

using ArmSamples = std::array<ArmSample, kArmCount>;

// Commanded joint velocity in raw counts per second (sign ignored).
using JointVelocity = std::array<double, kJointsPerArm>;

// Raw counts per second for one AX-12A Moving Speed unit: 0.111 rpm is
// 0.666 deg/s, and the project maps 300 deg to 1023 counts (about 2.27).
inline constexpr double kCountsPerSecondPerSpeedUnit = 0.111 * 6.0 * 1023.0 / 300.0;

// With Moving Speed 0 (the power-up value is unknown) each small AX step runs at
// full speed and then waits for the next one, which made the arms stutter and
// sway. Every AX therefore carries a speed that lets the motor keep moving
// until the next command arrives.
struct SpeedOptions
{
  double gain{1.2};         // lead on the commanded velocity, so the motor does not fall behind
  double catch_up_s{0.25};  // a remaining error is closed in about this time
  int min_speed{20};        // about 13 deg/s, so the last counts still arrive
  int max_speed{300};       // about 200 deg/s
};

// Moving Speed for one joint: the commanded velocity with some lead, or enough to
// close the present error, whichever is faster, clamped to [min_speed, max_speed].
std::uint16_t moving_speed(double command_counts_per_s, int error_counts, const SpeedOptions & options) noexcept;

struct SchedulerOptions
{
  bool enable_motion{false};
  int max_step_raw{0};
  std::chrono::milliseconds min_cycle{10};
  SpeedOptions speed{};
};

// Owns the serial link while running, keeping blocking I/O off the control
// thread. Any error latches a fault: nothing further is sent, and no command is
// retried. Faults are final for this instance.
class Scheduler
{
public:
  // initial_targets holds poses already acknowledged before the scheduler started.
  Scheduler(
    Link & link, SchedulerOptions options, const std::array<RawPose, kArmCount> & initial,
    const std::array<std::optional<RawPose>, kArmCount> & initial_targets = {});
  ~Scheduler();
  Scheduler(const Scheduler &) = delete;
  Scheduler & operator=(const Scheduler &) = delete;

  void start();
  void stop();

  // Non-blocking, for the control thread. A false return means the lock was
  // busy and the caller should retry on its next cycle.
  // velocity is the commanded velocity behind target, used for Moving Speed.
  bool submit(Arm arm, const RawPose & target, const JointVelocity & velocity = {}) noexcept;
  bool snapshot(ArmSamples & samples) const noexcept;

  bool faulted() const noexcept { return faulted_.load(std::memory_order_acquire); }
  std::string fault() const;

private:
  void run(std::stop_token stop);
  bool cycle_arm(Arm arm);
  void latch(std::string reason);

  Link & link_;
  SchedulerOptions options_;
  std::array<RawPose, kArmCount> last_sent_;
  mutable std::mutex mutex_;
  std::array<std::optional<RawPose>, kArmCount> targets_{};
  std::array<JointVelocity, kArmCount> velocities_{};
  std::array<std::optional<RawPose>, kArmCount> acked_{};
  ArmSamples samples_{};
  std::string fault_;
  std::atomic<bool> faulted_{false};
  std::jthread worker_;
};

}  // namespace cm530_hardware
