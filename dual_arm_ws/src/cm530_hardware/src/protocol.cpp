#include "cm530_hardware/protocol.hpp"

#include <charconv>
#include <format>
#include <vector>

namespace cm530_hardware
{
namespace
{

std::vector<std::string_view> split_fields(std::string_view line)
{
  std::vector<std::string_view> fields;
  std::size_t start = 0;
  while (true) {
    const std::size_t comma = line.find(',', start);
    if (comma == std::string_view::npos) {
      fields.push_back(line.substr(start));
      return fields;
    }
    fields.push_back(line.substr(start, comma - start));
    start = comma + 1;
  }
}

// Unsigned parsing rejects signs; the full-consumption check rejects decimals.
std::optional<std::uint16_t> parse_value(std::string_view text, int max)
{
  unsigned value = 0;
  const char * const end = text.data() + text.size();
  const auto [ptr, error] = std::from_chars(text.data(), end, value);
  if (text.empty() || error != std::errc{} || ptr != end || value > static_cast<unsigned>(max)) {
    return std::nullopt;
  }
  return static_cast<std::uint16_t>(value);
}

using Group = std::array<std::uint16_t, kJointsPerArm>;

// tag,armN followed by one group of four values per entry of max, each value
// within 0..max of its group. Empty on any deviation.
template<std::size_t Groups>
std::optional<std::array<Group, Groups>> match_groups(
  std::string_view line, std::string_view tag, Arm arm, const std::array<int, Groups> & max)
{
  const auto fields = split_fields(line);
  if (fields.size() != 2 + Groups * kJointsPerArm || fields[0] != tag || fields[1] != arm_name(arm)) {
    return std::nullopt;
  }
  std::array<Group, Groups> groups{};
  for (std::size_t group = 0; group < Groups; ++group) {
    for (std::size_t joint = 0; joint < kJointsPerArm; ++joint) {
      const auto value = parse_value(fields[2 + group * kJointsPerArm + joint], max[group]);
      if (!value) {
        return std::nullopt;
      }
      groups[group][joint] = *value;
    }
  }
  return groups;
}

Reply mismatch()
{
  return {ReplyStatus::kMismatch, {}, {}, {}, {}};
}

Reply ok()
{
  return {ReplyStatus::kOk, {}, {}, {}, {}};
}

Reply match_exact(std::string_view line, std::string_view expected)
{
  return line == expected ? ok() : mismatch();
}

}  // namespace

std::string_view arm_name(Arm arm) noexcept
{
  return arm == Arm::kArm1 ? "arm1" : "arm2";
}

int signed_load(std::uint16_t raw) noexcept
{
  const int magnitude = raw & 1023;
  return (raw & 1024) ? -magnitude : magnitude;
}

bool valid_slope(int value) noexcept
{
  for (int step = 2; step <= 128; step *= 2) {
    if (value == step) {
      return true;
    }
  }
  return false;
}

std::string format_command(const Command & command)
{
  const std::string_view arm = arm_name(command.arm);
  switch (command.kind) {
    case CommandKind::kPing:
      return "PING\n";
    case CommandKind::kVersion:
      return "VERSION\n";
    case CommandKind::kGetHome:
      return std::format("GET_HOME,{}\n", arm);
    case CommandKind::kRead:
      return std::format("READ,{}\n", arm);
    case CommandKind::kHold:
      return std::format("HOLD,{}\n", arm);
    case CommandKind::kAx:
      if (command.speed) {
        const RawSpeed & speed = *command.speed;
        return std::format(
          "AX,{},{},{},{},{},{},{},{},{}\n", arm, command.pose[0], command.pose[1], command.pose[2],
          command.pose[3], speed[0], speed[1], speed[2], speed[3]);
      }
      return std::format(
        "AX,{},{},{},{},{}\n", arm, command.pose[0], command.pose[1], command.pose[2],
        command.pose[3]);
    case CommandKind::kTorque:
      return std::format("TORQUE,{},{}\n", arm, command.torque ? 1 : 0);
    case CommandKind::kSetCompliance: {
      const Compliance & c = command.compliance;
      return std::format(
        "COMP,{},{},{},{},{},{},{},{},{},{},{},{},{}\n", arm, c.margin[0], c.margin[1], c.margin[2],
        c.margin[3], c.slope[0], c.slope[1], c.slope[2], c.slope[3], c.punch[0], c.punch[1], c.punch[2],
        c.punch[3]);
    }
    case CommandKind::kGetCompliance:
      return std::format("GET_COMP,{}\n", arm);
    case CommandKind::kDiag:
      return std::format("DIAG,{}\n", arm);
  }
  return {};
}

Reply classify_reply(const Command & command, std::string_view line)
{
  if (line == "READY" || line.starts_with("READY,")) {
    return {ReplyStatus::kRestarted, {}, {}, {}, {}};
  }
  if (line.starts_with("ERR,")) {
    return {ReplyStatus::kDeviceError, {}, {}, {}, {}};
  }
  const std::string_view arm = arm_name(command.arm);
  switch (command.kind) {
    case CommandKind::kPing:
      return match_exact(line, "PONG");
    case CommandKind::kVersion:
      return match_exact(line, std::format("VERSION,{}", kProtocolVersion));
    case CommandKind::kGetHome: {
      const auto groups = match_groups<1>(line, "HOME", command.arm, {kMaxRaw});
      if (!groups) {
        return mismatch();
      }
      Reply reply = ok();
      reply.pose = (*groups)[0];
      return reply;
    }
    case CommandKind::kRead: {
      const auto groups = match_groups<2>(line, "POS", command.arm, {kMaxRaw, kMaxLoad});
      if (!groups) {
        return mismatch();
      }
      Reply reply = ok();
      reply.pose = (*groups)[0];
      reply.load = (*groups)[1];
      return reply;
    }
    case CommandKind::kHold:
      return match_exact(line, std::format("OK,HOLD,{}", arm));
    case CommandKind::kAx:
      return match_exact(line, std::format("OK,AX,{}", arm));
    case CommandKind::kTorque:
      return match_exact(line, std::format("OK,TORQUE,{},{}", arm, command.torque ? 1 : 0));
    case CommandKind::kSetCompliance:
      return match_exact(line, std::format("OK,COMP,{}", arm));
    case CommandKind::kGetCompliance: {
      // The firmware reports the registers as read; a slope that is not one of
      // the seven steps is still reported, so the caller can see it differs.
      const auto groups = match_groups<3>(line, "COMP", command.arm, {kMaxComplianceMargin, 255, kMaxPunch});
      if (!groups) {
        return mismatch();
      }
      Reply reply = ok();
      reply.compliance = Compliance{(*groups)[0], (*groups)[1], (*groups)[2]};
      return reply;
    }
    case CommandKind::kDiag: {
      const auto groups = match_groups<2>(line, "DIAG", command.arm, {255, 255});
      if (!groups) {
        return mismatch();
      }
      Reply reply = ok();
      reply.diagnostics = Diagnostics{(*groups)[0], (*groups)[1]};
      return reply;
    }
  }
  return mismatch();
}

}  // namespace cm530_hardware
