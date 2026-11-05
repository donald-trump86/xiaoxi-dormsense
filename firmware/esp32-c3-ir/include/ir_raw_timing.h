#ifndef XIAOXI_IR_RAW_TIMING_H
#define XIAOXI_IR_RAW_TIMING_H

#include <cstddef>
#include <cstdint>
#include <cstdio>

namespace xiaoxi {
namespace ir {

constexpr uint16_t kRawTimingMaxEntries = 300;
constexpr uint16_t kRawTimingPartEntries = 16;
constexpr uint16_t kRawTimingTickUs = 2;

// Entry zero is IRrecv's synthetic sentinel, not a measured idle gap.
inline bool format_raw_timing_part(const volatile uint16_t* ticks,
                                   uint16_t rawlen, bool overflow,
                                   uint32_t capture_sequence, uint16_t offset,
                                   char* out, size_t capacity) {
  const uint16_t kept = rawlen < kRawTimingMaxEntries
                            ? rawlen : kRawTimingMaxEntries;
  if (!ticks || !out || !capacity || !kept || offset >= kept ||
      offset % kRawTimingPartEntries != 0) return false;
  const uint16_t remaining = kept - offset;
  const uint16_t count = remaining < kRawTimingPartEntries
                             ? remaining : kRawTimingPartEntries;
  int written = std::snprintf(
      out, capacity,
      "raw_timing capture=%lu rawlen=%u kept=%u truncated=%u overflow=%u "
      "offset=%u count=%u unit=us times=",
      static_cast<unsigned long>(capture_sequence), rawlen, kept,
      rawlen > kept ? 1U : 0U, overflow ? 1U : 0U, offset, count);
  if (written < 0 || static_cast<size_t>(written) >= capacity) return false;
  size_t used = static_cast<size_t>(written);
  for (uint16_t i = 0; i < count; ++i) {
    const uint32_t duration = offset + i == 0 ? kRawTimingTickUs :
        static_cast<uint32_t>(ticks[offset + i]) * kRawTimingTickUs;
    written = std::snprintf(out + used, capacity - used, "%s%lu",
                            i ? "," : "",
                            static_cast<unsigned long>(duration));
    if (written < 0 || static_cast<size_t>(written) >= capacity - used)
      return false;
    used += static_cast<size_t>(written);
  }
  return true;
}

}  // namespace ir
}  // namespace xiaoxi

#endif
