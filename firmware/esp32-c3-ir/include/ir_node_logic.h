#pragma once
#include <cstdint>
#include <cstring>

namespace xiaoxi {
namespace ir {

constexpr uint8_t IR_RECV_PIN = 4;  // GPIO4 (IO4): IR receiver OUT (3.3V)
constexpr uint8_t IR_SEND_PIN = 3;  // GPIO3 (IO3): IR transmitter DAT
constexpr uint64_t LOOPBACK_NEC_CODE = 0x5A02A55AULL;
constexpr uint16_t LOOPBACK_NEC_BITS = 32;

enum CommandAction : uint8_t {
  ACTION_INVALID = 0,
  ACTION_IR_LOOPBACK_TEST = 1,
  ACTION_AC_PREVIEW = 2,
  ACTION_AC_TRANSMIT = 3,
};

enum AcMode : uint8_t {
  AC_MODE_INVALID = 0,
  AC_MODE_COOL = 1,
  AC_MODE_HEAT = 2,
  AC_MODE_DRY = 3,
  AC_MODE_FAN = 4,
  AC_MODE_AUTO = 5,
};

enum AcFan : uint8_t {
  AC_FAN_INVALID = 0,
  AC_FAN_AUTO = 1,
  AC_FAN_LOW = 2,
  AC_FAN_MEDIUM = 3,
  AC_FAN_HIGH = 4,
};

struct AcSpec {
  char protocol[24];
  bool power;
  AcMode mode;
  uint8_t temp_c;
  AcFan fan;
};

inline bool is_supported_ac_protocol(const char* name) {
  if (!name || !name[0]) return false;
  static const char* const kAllowed[] = {
      "GREE",      "KELVINATOR",    "MIDEA",         "COOLIX",
      "HAIER_AC",  "HAIER_AC_YRW02", "HAIER_AC176",  "TCL112AC",
      "AUX",       "DAIKIN",        "MITSUBISHI_AC", "HISENSE",
      "KELON",
  };
  for (const char* item : kAllowed) {
    if (std::strcmp(name, item) == 0) return true;
  }
  return false;
}

inline AcMode parse_ac_mode(const char* mode_str) {
  if (!mode_str) return AC_MODE_INVALID;
  if (std::strcmp(mode_str, "cool") == 0) return AC_MODE_COOL;
  if (std::strcmp(mode_str, "heat") == 0) return AC_MODE_HEAT;
  if (std::strcmp(mode_str, "dry") == 0) return AC_MODE_DRY;
  if (std::strcmp(mode_str, "fan") == 0) return AC_MODE_FAN;
  if (std::strcmp(mode_str, "auto") == 0) return AC_MODE_AUTO;
  return AC_MODE_INVALID;
}

inline AcFan parse_ac_fan(const char* fan_str) {
  if (!fan_str) return AC_FAN_INVALID;
  if (std::strcmp(fan_str, "auto") == 0) return AC_FAN_AUTO;
  if (std::strcmp(fan_str, "low") == 0) return AC_FAN_LOW;
  if (std::strcmp(fan_str, "medium") == 0) return AC_FAN_MEDIUM;
  if (std::strcmp(fan_str, "high") == 0) return AC_FAN_HIGH;
  return AC_FAN_INVALID;
}

inline bool validate_ac_spec(const char* protocol, bool power, const char* mode_str,
                             int temp_c, const char* fan_str, AcSpec& out) {
  if (!is_supported_ac_protocol(protocol)) return false;
  const AcMode mode = parse_ac_mode(mode_str);
  const AcFan fan = parse_ac_fan(fan_str);
  if (mode == AC_MODE_INVALID || fan == AC_FAN_INVALID) return false;
  if (temp_c < 16 || temp_c > 30) return false;
  std::memset(&out, 0, sizeof(out));
  std::strncpy(out.protocol, protocol, sizeof(out.protocol) - 1);
  out.power = power;
  out.mode = mode;
  out.temp_c = static_cast<uint8_t>(temp_c);
  out.fan = fan;
  return true;
}

inline bool is_valid_ttl(int ttl_seconds) {
  return ttl_seconds >= 1 && ttl_seconds <= 30;
}

inline bool matches_loopback_frame(const char* decode_type_name, uint64_t value, uint16_t bits) {
  if (!decode_type_name) return false;
  return std::strcmp(decode_type_name, "NEC") == 0 &&
         value == LOOPBACK_NEC_CODE &&
         bits == LOOPBACK_NEC_BITS;
}

class CommandDeduplicator {
 public:
  static constexpr size_t kCapacity = 8;
  static constexpr size_t kMaxIdLen = 40;

  CommandDeduplicator() : next_index_(0) {
    std::memset(ids_, 0, sizeof(ids_));
  }

  bool seen_or_record(const char* command_id) {
    if (!command_id || !command_id[0] || std::strlen(command_id) >= kMaxIdLen) {
      return true;  // Reject empty or oversized command_id as invalid/blocked.
    }
    for (size_t i = 0; i < kCapacity; ++i) {
      if (ids_[i][0] != '\0' && std::strcmp(ids_[i], command_id) == 0) {
        return true;
      }
    }
    std::strncpy(ids_[next_index_], command_id, kMaxIdLen - 1);
    ids_[next_index_][kMaxIdLen - 1] = '\0';
    next_index_ = (next_index_ + 1) % kCapacity;
    return false;
  }

 private:
  char ids_[kCapacity][kMaxIdLen];
  size_t next_index_;
};

}  // namespace ir
}  // namespace xiaoxi
