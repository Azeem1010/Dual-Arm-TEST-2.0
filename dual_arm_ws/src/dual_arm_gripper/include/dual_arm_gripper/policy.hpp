#pragma once
#include <charconv>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace dual_arm_gripper {
struct Command { std::uint64_t sequence; bool attach; std::string object; };
inline std::optional<Command> parse(std::string_view text) {
  if (text.size() > 64) return std::nullopt;
  const auto comma = text.find(',');
  if (comma == std::string_view::npos) return std::nullopt;
  std::uint64_t sequence{};
  auto [end,error] = std::from_chars(text.data(),text.data()+comma,sequence);
  if (error != std::errc{} || end != text.data()+comma || sequence==0) return std::nullopt;
  const auto rest = text.substr(comma+1);
  if (rest=="release") return Command{sequence,false,{}};
  constexpr std::string_view prefix = "attach,cap_";
  if (!rest.starts_with(prefix) || rest.size()!=prefix.size()+1 || rest.back()<'1' || rest.back()>'8') return std::nullopt;
  return Command{sequence,true,std::string(rest.substr(7))};
}
// Simulation contact envelope: cap radius 10 mm minus cup radius 9 mm.
// Vertical tolerance is the explicit simulation contact envelope, not a physical
// camera calibration threshold: 2 mm, because a cup tilted 9 deg is held about
// 1.4 mm higher (9 mm * sin 9 deg) so its rim does not stop on the cap; straight
// down it stays 0.3 mm above. Reject nonfinite and inverted cups.
// The cup may tilt up to 10 deg (cos 10 deg = 0.98481): a four-axis arm cannot reach
// slot 8 straight down. The simulation coordinator.yaml plans at most 9 deg
// (max_tool_tilt_deg), so 1 deg is left for tracking error.
constexpr double kMinDownwardAlignment = 0.98481;
inline bool contact_ok(double lateral_m,double vertical_m,double downward_alignment) {
  return std::isfinite(lateral_m) && std::isfinite(vertical_m) && std::isfinite(downward_alignment)
    && lateral_m>=0. && lateral_m<=.001 && std::abs(vertical_m)<=.002 && downward_alignment>=kMinDownwardAlignment && downward_alignment<=1.000001;
}
}
