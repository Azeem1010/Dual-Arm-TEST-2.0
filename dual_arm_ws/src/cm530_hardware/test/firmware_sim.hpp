#pragma once

// Runs the unmodified v19 bridge.c, ax12.c and dynamixel.c against a simulated
// AX-12A bus. Only the physical HAL is simulated. The firmware uses globals, so
// there is exactly one instance per process.

#include <string>
#include <string_view>

namespace cm530_test
{

enum class MotorFault { kNone, kNoReply, kOverheat };

struct Motor
{
  double present{512.0};
  int goal{512};
  int speed{0};  // Moving Speed register; 0 is the uncontrolled maximum
  bool torque{false};
  MotorFault fault{MotorFault::kNone};
  // v19 registers: Present Load (raw 0..2047), compliance, voltage, temperature.
  int load{0};
  int margin_cw{1};
  int margin_ccw{1};
  int slope_cw{32};
  int slope_ccw{32};
  int punch{32};
  int voltage{120};
  int temperature{30};
};

class FirmwareSim
{
public:
  static FirmwareSim & instance();

  // Restores eight motors to raw 512 with torque off, then boots the firmware.
  std::string reset_and_boot();
  // Feeds host bytes to the firmware parser and returns its output.
  std::string feed(std::string_view bytes);

  Motor motor(int id) const;
  void set_present(int id, int raw);
  void set_fault(int id, MotorFault fault);
  void set_load(int id, int raw);
  // Makes the CW slope differ from the CCW slope, as a motor that was set elsewhere.
  void set_slope_cw(int id, int slope);
  // When set, COMP leaves this motor's registers unchanged (a lost write).
  void set_ignore_compliance(int id, bool ignore);
  // Top speed in counts per second; zero moves instantly. A nonzero Moving Speed
  // limits a motor further, as on an AX-12A.
  void set_motor_rate(double counts_per_second);
  int goal_writes() const;
  int torque_writes() const;
  int compliance_writes() const;

private:
  FirmwareSim() = default;
};

}  // namespace cm530_test
