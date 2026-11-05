#pragma once

#include <ArduinoJson.h>
#include <IRac.h>
#include <IRrecv.h>
#include <IRutils.h>
#include <cmath>

namespace xiaoxi {
namespace ir {

inline bool format_learning_capture(const decode_results& saved,
                                    const char* session, uint32_t capture,
                                    char* out, size_t capacity) {
  StaticJsonDocument<JSON_OBJECT_SIZE(6) + JSON_OBJECT_SIZE(14)> document;
  const String protocol = typeToString(saved.decode_type);
  document["kind"] = "capture";
  document["session_id"] = session;
  document["capture"] = capture;
  document["protocol"] = protocol.c_str();
  document["bits"] = saved.bits;
  stdAc::state_t common{};
  if (!IRAcUtils::decodeToState(&saved, &common)) {
    document["state"] = nullptr;
  } else {
    JsonObject state = document.createNestedObject("state");
    state["power"] = common.power;
    state["mode"] = static_cast<int>(common.mode);
    const float temp = common.celsius ? common.degrees :
                       (common.degrees - 32.0F) * 5.0F / 9.0F;
    if (std::isfinite(temp)) state["temp_c"] = temp;
    else state["temp_c"] = nullptr;
    state["fan"] = static_cast<int>(common.fanspeed);
    // Only these two protocols have source-verified support masks here.
    for (const char* key : {"swingv", "swingh", "light", "turbo", "econo",
                            "clean", "sleep", "ifeel", "quiet", "filter"})
      state[key] = nullptr;
    if (saved.decode_type == GREE || saved.decode_type == KELVINATOR) {
      state["swingv"] = static_cast<int>(common.swingv);
      state["swingh"] = static_cast<int>(common.swingh);
      state["light"] = common.light;
      state["turbo"] = common.turbo;
      state["clean"] = common.clean;
      if (saved.decode_type == GREE) {
        state["econo"] = common.econo;
        state["sleep"] = common.sleep;
        state["ifeel"] = common.iFeel;
      } else {
        state["quiet"] = common.quiet;
        state["filter"] = common.filter;
      }
    }
  }
  // bits is the library's decoded segment; raw chunks retain the entire input.
  if (document.overflowed() || measureJson(document) > 512 ||
      measureJson(document) >= capacity) return false;
  serializeJson(document, out, capacity);
  return true;
}

}  // namespace ir
}  // namespace xiaoxi
