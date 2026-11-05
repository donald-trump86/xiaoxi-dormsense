#pragma once

#include <ArduinoJson.h>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include "ir_node_logic.h"

namespace xiaoxi {
namespace ir {

constexpr size_t kMaxCommandBytes = 2560;
constexpr uint16_t kMaxReplayEntries = 299;
constexpr uint32_t kReplayLifetimeMs = 10000;
constexpr size_t kCommandJsonCapacity =
    JSON_OBJECT_SIZE(12) + JSON_ARRAY_SIZE(kMaxReplayEntries) + 768;

enum class WireAction { Invalid, Status, Start, Cancel, Prepare, Commit,
                        Loopback, AcPreview, AcSend };

struct WireCommand {
  WireAction action = WireAction::Invalid;
  char command_id[41] = {};
  char session_id[41] = {};
  char challenge[33] = {};
  uint32_t deadline_ms = 0;
  uint8_t window_seconds = 0;
  uint16_t timing_count = 0;
  uint16_t timings[kMaxReplayEntries] = {};
  AcSpec spec{};
  char mode[8] = {};
  char fan[8] = {};
};

inline bool before_deadline(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(deadline - now) > 0;
}

inline bool safe_id(JsonVariantConst value, char* out, size_t max_length) {
  if (!value.is<const char*>()) return false;
  const JsonString text = value.as<JsonString>();
  if (!text.size() || text.size() > max_length) return false;
  for (size_t i = 0; i < text.size(); ++i) {
    const char c = text.c_str()[i];
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
  }
  std::memcpy(out, text.c_str(), text.size());
  out[text.size()] = '\0';
  return true;
}

inline bool string_equals(JsonVariantConst value, const char* expected) {
  return value.is<const char*>() &&
      value.as<JsonString>().size() == std::strlen(expected) &&
      std::strcmp(value.as<const char*>(), expected) == 0;
}

// ArduinoJson accepts duplicate members and some non-JSON syntax. Restrict the
// wire to flat canonical strings/uints/bools and one uint array before parsing.
// Escapes are unnecessary for the protocol's ASCII identifiers and enum names.
class CommandSyntax {
 public:
  CommandSyntax(const char* data, size_t size) : data_(data), size_(size) {}
  bool valid(size_t& members) {
    members = 0;
    if (!take('{')) return false;
    if (take('}')) return end();
    do {
      if (!quoted() || !take(':') || !value()) return false;
      ++members;
      if (members > 12) return false;
      if (take('}')) return end();
    } while (take(','));
    return false;
  }

 private:
  void whitespace() {
    while (pos_ < size_ && (data_[pos_] == ' ' || data_[pos_] == '\t' ||
           data_[pos_] == '\r' || data_[pos_] == '\n')) ++pos_;
  }
  bool take(char c) {
    whitespace();
    if (pos_ == size_ || data_[pos_] != c) return false;
    ++pos_;
    return true;
  }
  bool end() { whitespace(); return pos_ == size_; }
  bool quoted() {
    if (!take('"')) return false;
    while (pos_ < size_) {
      const unsigned char c = data_[pos_++];
      if (c == '"') return true;
      if (c < 32 || c > 126 || c == '\\') return false;
    }
    return false;
  }
  bool number() {
    whitespace();
    if (pos_ == size_ || data_[pos_] < '0' || data_[pos_] > '9') return false;
    if (data_[pos_++] == '0') return true;
    while (pos_ < size_ && data_[pos_] >= '0' && data_[pos_] <= '9') ++pos_;
    return true;
  }
  bool value() {
    whitespace();
    if (pos_ == size_) return false;
    if (data_[pos_] == '"') return quoted();
    if (take('[')) {
      if (take(']')) return true;
      size_t count = 0;
      do {
        if (!number() || ++count > kMaxReplayEntries) return false;
        if (take(']')) return true;
      } while (take(','));
      return false;
    }
    for (const char* literal : {"true", "false"}) {
      const size_t length = std::strlen(literal);
      if (size_ - pos_ >= length &&
          std::memcmp(data_ + pos_, literal, length) == 0) {
        pos_ += length;
        return true;
      }
    }
    return number();
  }
  const char* data_;
  size_t size_;
  size_t pos_ = 0;
};

class CommandParser {
 public:
  bool parse(const char* input, size_t length, const char* live_boot,
             uint32_t now, WireCommand& out) {
    out = WireCommand{};
    size_t members = 0;
    if (!input || !length || length > kMaxCommandBytes ||
        !CommandSyntax(input, length).valid(members)) return false;
    document_.clear();
    if (deserializeJson(document_, input, length,
                        DeserializationOption::NestingLimit(2))) return false;
    const JsonObjectConst obj = document_.as<JsonObjectConst>();
    if (obj.isNull() || obj.size() != members ||
        !string_equals(obj["schema_version"], "1.0") ||
        !string_equals(obj["node_id"], "node02") ||
        !safe_id(obj["command_id"], out.command_id, 40) ||
        !obj["ttl_seconds"].is<unsigned int>() ||
        !is_valid_ttl(obj["ttl_seconds"].as<unsigned int>())) return false;
    const JsonVariantConst action = obj["action"];
    if (string_equals(action, "ir_status")) out.action = WireAction::Status;
    else if (string_equals(action, "ir_learn_start")) out.action = WireAction::Start;
    else if (string_equals(action, "ir_learn_cancel")) out.action = WireAction::Cancel;
    else if (string_equals(action, "ir_raw_prepare")) out.action = WireAction::Prepare;
    else if (string_equals(action, "ir_raw_commit")) out.action = WireAction::Commit;
    else if (string_equals(action, "ir_loopback_test")) out.action = WireAction::Loopback;
    else if (string_equals(action, "ac_preview")) out.action = WireAction::AcPreview;
    else if (string_equals(action, "ac_send")) out.action = WireAction::AcSend;
    else return false;

    const bool learning_action = out.action <= WireAction::Commit;
    if (learning_action && out.action != WireAction::Status) {
      if (!string_equals(obj["boot_id"], live_boot) ||
          !obj["deadline_ms"].is<uint32_t>()) return false;
      out.deadline_ms = obj["deadline_ms"].as<uint32_t>();
      const int32_t remaining = static_cast<int32_t>(out.deadline_ms - now);
      if (remaining <= 0 || remaining > 10000) return false;
    }
    if (learning_action) {
      for (JsonPairConst field : obj) {
        const char* name = field.key().c_str();
        bool allowed = std::strcmp(name, "schema_version") == 0 ||
            std::strcmp(name, "node_id") == 0 ||
            std::strcmp(name, "action") == 0 ||
            std::strcmp(name, "command_id") == 0 ||
            std::strcmp(name, "ttl_seconds") == 0;
        if (out.action != WireAction::Status)
          allowed |= std::strcmp(name, "boot_id") == 0 ||
                     std::strcmp(name, "deadline_ms") == 0;
        if (out.action == WireAction::Start || out.action == WireAction::Cancel)
          allowed |= std::strcmp(name, "session_id") == 0;
        if (out.action == WireAction::Start)
          allowed |= std::strcmp(name, "window_seconds") == 0;
        if (out.action == WireAction::Prepare)
          allowed |= std::strcmp(name, "frequency_khz") == 0 ||
                     std::strcmp(name, "timings_us") == 0;
        if (out.action == WireAction::Commit)
          allowed |= std::strcmp(name, "challenge") == 0;
        if (!allowed) return false;
      }
    }
    if (out.action == WireAction::Start || out.action == WireAction::Cancel) {
      if (!safe_id(obj["session_id"], out.session_id, 40)) return false;
    }
    if (out.action == WireAction::Start) {
      if (!obj["window_seconds"].is<unsigned int>()) return false;
      const unsigned int seconds = obj["window_seconds"].as<unsigned int>();
      if (seconds < 1 || seconds > 60) return false;
      out.window_seconds = seconds;
    }
    if (out.action == WireAction::Prepare) {
      if (!obj["frequency_khz"].is<unsigned int>() ||
          obj["frequency_khz"].as<unsigned int>() != 38 ||
          !obj["timings_us"].is<JsonArrayConst>()) return false;
      const JsonArrayConst timings = obj["timings_us"].as<JsonArrayConst>();
      if (timings.size() < 15 || timings.size() > kMaxReplayEntries ||
          timings.size() % 2 == 0) return false;
      uint32_t total = 0;
      for (JsonVariantConst timing : timings) {
        if (!timing.is<unsigned int>()) return false;
        const unsigned int duration = timing.as<unsigned int>();
        if (!duration || duration > 65535 || (total += duration) > 1000000U)
          return false;
        out.timings[out.timing_count++] = duration;
      }
    }
    if (out.action == WireAction::Commit) {
      if (!safe_id(obj["challenge"], out.challenge, 32) ||
          std::strlen(out.challenge) != 32) return false;
      for (const char* p = out.challenge; *p; ++p)
        if (!((*p >= '0' && *p <= '9') || (*p >= 'a' && *p <= 'f'))) return false;
    }
    if (out.action == WireAction::AcPreview || out.action == WireAction::AcSend) {
      char protocol[24] = {};
      if (!safe_id(obj["protocol"], protocol, 23) ||
          !safe_id(obj["mode"], out.mode, 7) ||
          !safe_id(obj["fan"], out.fan, 7) ||
          !obj["power"].is<bool>() || !obj["temp_c"].is<unsigned int>() ||
          obj["temp_c"].as<unsigned int>() > 30 ||
          !validate_ac_spec(protocol, obj["power"].as<bool>(), out.mode,
                            obj["temp_c"].as<unsigned int>(), out.fan, out.spec))
        return false;
    }
    return true;
  }

 private:
  StaticJsonDocument<kCommandJsonCapacity> document_;
};

class LearningWindow {
 public:
  bool armed = false;
  char session_id[41] = {};
  uint32_t expires_ms = 0;

  void start(const WireCommand& command, uint32_t now) {
    std::strcpy(session_id, command.session_id);
    expires_ms = now + command.window_seconds * 1000U;
    armed = true;
  }
  bool expire(uint32_t now) {
    if (!armed || before_deadline(now, expires_ms)) return false;
    armed = false;
    return true;
  }
  bool cancel(const char* session) {
    if (!armed || std::strcmp(session_id, session) != 0) return false;
    armed = false;
    return true;
  }
  bool consume(uint32_t now, char* session) {
    if (!armed || !before_deadline(now, expires_ms)) return false;
    armed = false;  // Consume before any event publication.
    std::strcpy(session, session_id);
    return true;
  }
};

struct RawWaveform {
  uint16_t count = 0;
  uint16_t timings[kMaxReplayEntries] = {};
};

class RawPreparation {
 public:
  void clear() {
    waveform_ = RawWaveform{};
    std::memset(challenge_, 0, sizeof(challenge_));
    expires_ms = 0;
    pending = false;
  }
  void prepare(const WireCommand& command, const char* challenge, uint32_t now) {
    clear();
    waveform_.count = command.timing_count;
    std::memcpy(waveform_.timings, command.timings,
                waveform_.count * sizeof(uint16_t));
    std::strcpy(challenge_, challenge);
    expires_ms = now + kReplayLifetimeMs;
    pending = true;
  }
  void expire(uint32_t now) {
    if (pending && !before_deadline(now, expires_ms)) clear();
  }
  bool take(const char* challenge, uint32_t now, RawWaveform& out) {
    expire(now);
    if (!pending || std::strcmp(challenge_, challenge) != 0) return false;
    out = waveform_;
    clear();  // The caller gets the only remaining copy before sendRaw().
    return true;
  }
  bool pending = false;
  uint32_t expires_ms = 0;

 private:
  RawWaveform waveform_;
  char challenge_[33] = {};
};

inline bool format_event_envelope(const char* boot_id, uint32_t sequence,
                                  const char* event_type, const char* severity,
                                  const char* detail, char* out, size_t capacity) {
  if (!detail || std::strlen(detail) > 512) return false;
  StaticJsonDocument<JSON_OBJECT_SIZE(9)> event;
  event["schema_version"] = "1.0";
  event["node_id"] = "node02";
  event["boot_id"] = boot_id;
  event["sequence"] = sequence;
  event["timestamp"] = nullptr;
  event["simulated"] = false;
  event["event_type"] = event_type;
  event["severity"] = severity;
  event["detail"] = detail;
  if (event.overflowed() || measureJson(event) >= capacity) return false;
  serializeJson(event, out, capacity);
  return true;
}

}  // namespace ir
}  // namespace xiaoxi
