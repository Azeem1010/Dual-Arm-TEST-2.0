#include "firmware_sim.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <map>
#include <mutex>
#include <utility>
#include <vector>

extern "C" {
#include "bridge.h"
#include "dxl_hal.h"
#include "dynamixel.h"
}

namespace cm530_test
{
namespace
{

constexpr unsigned char kInstRead = 2;
constexpr unsigned char kInstSyncWrite = 0x83;
constexpr unsigned char kOverheatBit = 4;
constexpr int kTimeoutPolls = 100;

struct State
{
  mutable std::recursive_mutex mutex;
  std::map<int, Motor> motors;
  std::string output;
  std::vector<unsigned char> rx;
  std::size_t rx_used{0};
  int polls{0};
  int goal_writes{0};
  int torque_writes{0};
  int compliance_writes{0};
  std::map<int, bool> ignore_compliance;
  double rate{0.0};
  std::chrono::steady_clock::time_point last_update{std::chrono::steady_clock::now()};
};

State & state()
{
  static State instance;
  return instance;
}

void advance_motors()
{
  State & s = state();
  const auto now = std::chrono::steady_clock::now();
  const double dt = std::chrono::duration<double>(now - s.last_update).count();
  s.last_update = now;
  for (auto & [id, motor] : s.motors) {
    if (!motor.torque) {
      continue;
    }
    if (s.rate <= 0.0) {
      motor.present = motor.goal;
      continue;
    }
    const double error = motor.goal - motor.present;
    // AX-12A Moving Speed: about 2.27 counts per second per unit.
    const double rate = motor.speed > 0 ? std::min(s.rate, motor.speed * 0.111 * 6.0 * 1023.0 / 300.0) : s.rate;
    const double step = std::min(std::abs(error), rate * dt);
    motor.present += std::copysign(step, error);
  }
}

void apply_sync_write(const unsigned char * packet)
{
  State & s = state();
  const int address = packet[5];
  const int width = packet[6];
  const int count = (packet[3] - 4) / (width + 1);
  for (int block = 0; block < count; ++block) {
    const unsigned char * entry = packet + 7 + block * (width + 1);
    const auto found = s.motors.find(entry[0]);
    if (found == s.motors.end()) {
      std::abort();
    }
    Motor & motor = found->second;
    const bool ignored = s.ignore_compliance[entry[0]];
    if (address == 30 && width == 4) {
      motor.goal = entry[1] + 256 * entry[2];
      motor.speed = entry[3] + 256 * entry[4];
    } else if (address == 24 && width == 1) {
      motor.torque = entry[1] != 0;
    } else if (address == 26 && width == 4) {
      if (!ignored) {
        motor.margin_cw = entry[1];
        motor.margin_ccw = entry[2];
        motor.slope_cw = entry[3];
        motor.slope_ccw = entry[4];
      }
    } else if (address == 48 && width == 2) {
      if (!ignored) {
        motor.punch = entry[1] + 256 * entry[2];
      }
    } else {
      std::abort();
    }
  }
  if (address == 30) {
    s.goal_writes++;
  } else if (address == 24) {
    s.torque_writes++;
  } else {
    s.compliance_writes++;
  }
}

// Register file up to address 49 as an AX-12A would report it.
std::array<int, 50> registers(const Motor & motor)
{
  std::array<int, 50> r{};
  const int position = static_cast<int>(std::lround(motor.present));
  r[24] = motor.torque ? 1 : 0;
  r[26] = motor.margin_cw;
  r[27] = motor.margin_ccw;
  r[28] = motor.slope_cw;
  r[29] = motor.slope_ccw;
  r[30] = motor.goal & 0xFF;
  r[31] = motor.goal >> 8;
  r[32] = motor.speed & 0xFF;
  r[33] = motor.speed >> 8;
  r[36] = position & 0xFF;
  r[37] = position >> 8;
  r[40] = motor.load & 0xFF;
  r[41] = motor.load >> 8;
  r[42] = motor.voltage;
  r[43] = motor.temperature;
  r[48] = motor.punch & 0xFF;
  r[49] = motor.punch >> 8;
  return r;
}

void queue_status(int id, const Motor & motor, int address, int length)
{
  State & s = state();
  const auto r = registers(motor);
  std::vector<unsigned char> reply{
    0xFF, 0xFF, static_cast<unsigned char>(id), static_cast<unsigned char>(length + 2),
    static_cast<unsigned char>(motor.fault == MotorFault::kOverheat ? kOverheatBit : 0)};
  for (int offset = 0; offset < length; ++offset) {
    reply.push_back(static_cast<unsigned char>(r[static_cast<std::size_t>(address + offset)]));
  }
  unsigned char sum = 0;
  for (std::size_t index = 2; index < reply.size(); ++index) {
    sum = static_cast<unsigned char>(sum + reply[index]);
  }
  reply.push_back(static_cast<unsigned char>(~sum));
  s.rx = std::move(reply);
  s.rx_used = 0;
}

}  // namespace

FirmwareSim & FirmwareSim::instance()
{
  static FirmwareSim sim;
  return sim;
}

std::string FirmwareSim::reset_and_boot()
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  s.motors.clear();
  for (const int id : {17, 3, 2, 15, 12, 1, 8, 16}) {
    s.motors[id] = Motor{};
  }
  s.rx.clear();
  s.rx_used = 0;
  s.rate = 0.0;
  s.goal_writes = 0;
  s.torque_writes = 0;
  s.compliance_writes = 0;
  s.ignore_compliance.clear();
  s.output.clear();
  dxl_initialize(0, 1);
  BridgeInit();
  s.torque_writes = 0;
  return std::exchange(s.output, {});
}

std::string FirmwareSim::feed(std::string_view bytes)
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  for (const char value : bytes) {
    BridgeFeed(static_cast<unsigned char>(value));
  }
  return std::exchange(s.output, {});
}

Motor FirmwareSim::motor(int id) const
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  advance_motors();
  return s.motors.at(id);
}

void FirmwareSim::set_present(int id, int raw)
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  s.motors.at(id).present = raw;
}

void FirmwareSim::set_fault(int id, MotorFault fault)
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  s.motors.at(id).fault = fault;
}

void FirmwareSim::set_motor_rate(double counts_per_second)
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  s.rate = counts_per_second;
}

int FirmwareSim::goal_writes() const
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  return s.goal_writes;
}

void FirmwareSim::set_load(int id, int raw)
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  s.motors.at(id).load = raw;
}

void FirmwareSim::set_slope_cw(int id, int slope)
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  s.motors.at(id).slope_cw = slope;
}

void FirmwareSim::set_ignore_compliance(int id, bool ignore)
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  s.ignore_compliance[id] = ignore;
}

int FirmwareSim::compliance_writes() const
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  return s.compliance_writes;
}

int FirmwareSim::torque_writes() const
{
  State & s = state();
  const std::scoped_lock lock(s.mutex);
  return s.torque_writes;
}

}  // namespace cm530_test

extern "C" {

void BridgeOutput(const char * text)
{
  cm530_test::state().output += text;
}

void BridgeSetArmLed(int, int) {}

int dxl_hal_open(int, int)
{
  return 1;
}

void dxl_hal_close(void) {}

void dxl_hal_clear(void)
{
  auto & s = cm530_test::state();
  s.rx.clear();
  s.rx_used = 0;
}

void dxl_hal_set_timeout(int)
{
  cm530_test::state().polls = 0;
}

int dxl_hal_timeout(void)
{
  return ++cm530_test::state().polls > cm530_test::kTimeoutPolls;
}

int dxl_hal_rx(unsigned char * packet, int count)
{
  auto & s = cm530_test::state();
  int taken = 0;
  while (taken < count && s.rx_used < s.rx.size()) {
    packet[taken++] = s.rx[s.rx_used++];
  }
  return taken;
}

int dxl_hal_tx(unsigned char * packet, int count)
{
  auto & s = cm530_test::state();
  cm530_test::advance_motors();
  s.rx.clear();
  s.rx_used = 0;
  if (packet[4] == cm530_test::kInstSyncWrite) {
    cm530_test::apply_sync_write(packet);
  } else if (packet[4] == cm530_test::kInstRead) {
    const int address = packet[5];
    const int length = packet[6];
    if (!((address == 36 && length == 6) || (address == 26 && length == 24) || (address == 42 && length == 2))) {
      std::abort();
    }
    const auto found = s.motors.find(packet[2]);
    if (found != s.motors.end() && found->second.fault != cm530_test::MotorFault::kNoReply) {
      cm530_test::queue_status(packet[2], found->second, address, length);
    }
  } else {
    std::abort();
  }
  return count;
}

}  // extern "C"
