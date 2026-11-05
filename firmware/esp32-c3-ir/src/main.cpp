#include <Arduino.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <IRremoteESP8266.h>
#include <IRrecv.h>
#include <IRsend.h>
#include <IRac.h>
#include <IRutils.h>
#include <esp_system.h>
#include <cstdio>
#include <cstring>

#include "ir_node_logic.h"
#include "ir_raw_timing.h"
#include "ir_learning.h"
#include "ir_learning_capture.h"
#include "secrets.h"

namespace _IRrecv {
extern atomic_irparams_t params;
}

namespace {

constexpr char STATUS_TOPIC[] = "xiaoxi/dorm/node02/status";
constexpr char EVENT_TOPIC[] = "xiaoxi/dorm/node02/event";
constexpr char COMMAND_TOPIC[] = "xiaoxi/dorm/node02/command";
constexpr char OFFLINE_PAYLOAD[] =
    "{\"schema_version\":\"1.0\",\"node_id\":\"node02\",\"state\":\"offline\"}";
constexpr char ONLINE_PAYLOAD[] =
    "{\"schema_version\":\"1.0\",\"node_id\":\"node02\",\"state\":\"online\"}";

IRrecv irrecv(xiaoxi::ir::IR_RECV_PIN, 1024, 50, true);
IRsend irsend(xiaoxi::ir::IR_SEND_PIN);
IRac ac(xiaoxi::ir::IR_SEND_PIN);
decode_results ir_results;

WiFiClientSecure tls_client;
PubSubClient mqtt(tls_client);
Preferences prefs;
xiaoxi::ir::CommandDeduplicator dedup;
xiaoxi::ir::CommandParser command_parser;
xiaoxi::ir::WireCommand command;
xiaoxi::ir::LearningWindow learning;
xiaoxi::ir::RawPreparation preparation;
xiaoxi::ir::RawWaveform sending_waveform;

char boot_id[24] = {};
uint32_t sequence = 0;
int8_t ir_cal_offset = 0;
uint32_t last_network_ms = 0;
uint32_t last_retry_ms = 0;
uint32_t retry_backoff_ms = 1000;
bool mqtt_online = false;
bool raw_timing_pending = false;
static_assert(kRawTick == xiaoxi::ir::kRawTimingTickUs, "IR raw tick changed");

void init_boot_id() {
  prefs.begin("xiaoxi02", false);
  uint32_t counter = prefs.getUInt("boot", 0) + 1U;
  prefs.putUInt("boot", counter);
  prefs.end();
  std::snprintf(boot_id, sizeof(boot_id), "node02-%08lx",
                static_cast<unsigned long>(counter));
}

void publish_event(const char* event_type, const char* severity,
                   const char* detail) {
  char payload[1024] = {};
  if (!xiaoxi::ir::format_event_envelope(boot_id, sequence, event_type, severity,
                                        detail, payload, sizeof(payload))) return;
  ++sequence;
  bool sent = false;
  if (mqtt_online && mqtt.connected()) {
    sent = mqtt.publish(EVENT_TOPIC, payload, false);
  }
  Serial.printf("ir_event_transmitted=%s detail=%s\n", sent ? "true" : "false",
                detail);
}

void publish_raw_timing_once() {
  if (!raw_timing_pending) return;
  raw_timing_pending = false;
  const uint32_t capture_sequence = sequence;
  const uint16_t kept = std::min<uint16_t>(
      ir_results.rawlen, xiaoxi::ir::kRawTimingMaxEntries);
  for (uint16_t offset = 0; offset < kept;
       offset += xiaoxi::ir::kRawTimingPartEntries) {
    char detail[320] = {};
    if (!xiaoxi::ir::format_raw_timing_part(
            ir_results.rawbuf, ir_results.rawlen, ir_results.overflow,
            capture_sequence, offset, detail, sizeof(detail))) return;
    publish_event("ir_raw_timing", "info", detail);
  }
}

void run_safe_loopback_test(const char* trigger_source, bool capture_raw = false) {
  raw_timing_pending = capture_raw;
  const uint16_t before_rawlen = _IRrecv::params.rawlen;
  const int pin_before = digitalRead(xiaoxi::ir::IR_RECV_PIN);
  Serial.printf("ir_loopback_tx_start=true source=%s pin_tx=%u pin_rx=%u\n",
                trigger_source, xiaoxi::ir::IR_SEND_PIN,
                xiaoxi::ir::IR_RECV_PIN);
  // Keep IRrecv interrupt enabled so GPIO4 captures GPIO3's 38kHz optical burst
  irsend.sendNEC(xiaoxi::ir::LOOPBACK_NEC_CODE, xiaoxi::ir::LOOPBACK_NEC_BITS);
  delay(70);
  const uint16_t after_rawlen = _IRrecv::params.rawlen;
  if (after_rawlen == 0) raw_timing_pending = false;
  const uint8_t after_state = _IRrecv::params.rcvstate;
  if (after_rawlen > 0 && after_state != 5) {
    _IRrecv::params.rcvstate = 5;  // kStopState fallback if ESP32-C3 timer ISR did not fire
  }
  char diag[192] = {};
  std::snprintf(diag, sizeof(diag),
                "loopback_tx_done src=%s cal_offset=%d rx_pin_idle=%d "
                "rawlen_before=%u rawlen_after=%u rcvstate=%u",
                trigger_source, static_cast<int>(ir_cal_offset), pin_before,
                before_rawlen, after_rawlen, after_state);
  publish_event("ir_loopback_diag", "info", diag);
}

stdAc::opmode_t to_stdac_mode(xiaoxi::ir::AcMode mode) {
  switch (mode) {
    case xiaoxi::ir::AC_MODE_COOL:
      return stdAc::opmode_t::kCool;
    case xiaoxi::ir::AC_MODE_HEAT:
      return stdAc::opmode_t::kHeat;
    case xiaoxi::ir::AC_MODE_DRY:
      return stdAc::opmode_t::kDry;
    case xiaoxi::ir::AC_MODE_FAN:
      return stdAc::opmode_t::kFan;
    default:
      return stdAc::opmode_t::kAuto;
  }
}

stdAc::fanspeed_t to_stdac_fan(xiaoxi::ir::AcFan fan) {
  switch (fan) {
    case xiaoxi::ir::AC_FAN_LOW:
      return stdAc::fanspeed_t::kLow;
    case xiaoxi::ir::AC_FAN_MEDIUM:
      return stdAc::fanspeed_t::kMedium;
    case xiaoxi::ir::AC_FAN_HIGH:
      return stdAc::fanspeed_t::kHigh;
    default:
      return stdAc::fanspeed_t::kAuto;
  }
}

void publish_learning(JsonDocument& document) {
  char detail[513] = {};
  if (document.overflowed() || measureJson(document) > 512) return;
  serializeJson(document, detail, sizeof(detail));
  publish_event("ir_learning", "info", detail);
}

void publish_session_end(const char* kind, const char* session,
                         const char* command_id = nullptr) {
  StaticJsonDocument<JSON_OBJECT_SIZE(3)> reply;
  reply["kind"] = kind;
  reply["session_id"] = session;
  if (command_id) reply["command_id"] = command_id;
  publish_learning(reply);
}

void expire_learning_state(uint32_t now) {
  if (learning.expire(now)) publish_session_end("expired", learning.session_id);
  preparation.expire(now);
}

void on_mqtt_message(char* topic, byte* payload, unsigned int length) {
  using xiaoxi::ir::WireAction;
  if (!topic || std::strcmp(topic, COMMAND_TOPIC) != 0) return;
  const uint32_t now = millis();
  expire_learning_state(now);
  if (!command_parser.parse(reinterpret_cast<const char*>(payload), length,
                            boot_id, now, command)) {
    publish_event("command_rejected", "warning", "invalid_command_or_deadline");
    return;
  }
  if (dedup.seen_or_record(command.command_id)) {
    publish_event("command_rejected", "warning", "duplicate_command_id");
    return;
  }
  const char* command_id = command.command_id;
  if (command.action == WireAction::Status) {
    StaticJsonDocument<JSON_OBJECT_SIZE(4)> reply;
    reply["kind"] = "status";
    reply["command_id"] = command_id;
    reply["version"] = "learn1";
    reply["uptime_ms"] = millis();
    publish_learning(reply);
    return;
  }
  if (command.action == WireAction::Start) {
    if (learning.armed) {
      publish_event("command_rejected", "warning", "learning_busy");
      return;
    }
    preparation.clear();
    raw_timing_pending = false;
    irrecv.disableIRIn();
    irrecv.enableIRIn(true);  // Discard all pre-window receiver data.
    learning.start(command, millis());
    StaticJsonDocument<JSON_OBJECT_SIZE(4)> reply;
    reply["kind"] = "ready";
    reply["session_id"] = static_cast<const char*>(command.session_id);
    reply["command_id"] = command_id;
    reply["window_seconds"] = command.window_seconds;
    publish_learning(reply);
    return;
  }
  if (command.action == WireAction::Cancel) {
    if (!learning.cancel(command.session_id)) {
      publish_event("command_rejected", "warning", "no_matching_learning_session");
      return;
    }
    preparation.clear();
    raw_timing_pending = false;
    irrecv.resume();
    publish_session_end("cancelled", command.session_id, command_id);
    return;
  }
  if (command.action == WireAction::Prepare) {
    if (learning.armed) {
      publish_event("command_rejected", "warning", "learning_busy");
      return;
    }
    char challenge[33] = {};
    uint8_t random_bytes[16];
    esp_fill_random(random_bytes, sizeof(random_bytes));
    for (size_t i = 0; i < sizeof(random_bytes); ++i)
      std::snprintf(challenge + 2 * i, 3, "%02x", random_bytes[i]);
    preparation.prepare(command, challenge, millis());
    StaticJsonDocument<JSON_OBJECT_SIZE(4)> reply;
    reply["kind"] = "prepared";
    reply["command_id"] = command_id;
    reply["challenge"] = static_cast<const char*>(challenge);
    reply["expires_ms"] = preparation.expires_ms;
    publish_learning(reply);
    return;
  }
  if (command.action == WireAction::Commit) {
    if (learning.armed || !preparation.take(command.challenge, millis(),
                                           sending_waveform)) {
      publish_event("command_rejected", "warning", "invalid_or_expired_challenge");
      return;
    }
    raw_timing_pending = false;
    irrecv.disableIRIn();
    irsend.sendRaw(sending_waveform.timings, sending_waveform.count, 38);
    irrecv.enableIRIn(true);
    sending_waveform = xiaoxi::ir::RawWaveform{};
    StaticJsonDocument<JSON_OBJECT_SIZE(2)> reply;
    reply["kind"] = "sent";
    reply["command_id"] = command_id;
    publish_learning(reply);
    return;
  }
  if (command.action == WireAction::Loopback) {
    if (learning.armed) {
      publish_event("command_rejected", "warning", "learning_busy");
      return;
    }
    run_safe_loopback_test(command_id);
    return;
  }
  if (command.action == WireAction::AcPreview ||
      command.action == WireAction::AcSend) {
    const bool live_send = command.action == WireAction::AcSend;
    if (live_send && learning.armed) {
      publish_event("command_rejected", "warning", "learning_busy");
      return;
    }
    const auto& spec = command.spec;
    const decode_type_t proto_enum = strToDecodeType(spec.protocol);
    const bool lib_supported = IRac::isProtocolSupported(proto_enum);
    if (!lib_supported) {
      publish_event("command_rejected", "warning", "unsupported_ac_protocol");
      return;
    }
    IRac::initState(&ac.next);
    ac.next.protocol = proto_enum;
    ac.next.power = spec.power;
    ac.next.mode = to_stdac_mode(spec.mode);
    ac.next.degrees = spec.temp_c;
    ac.next.celsius = true;
    ac.next.fanspeed = to_stdac_fan(spec.fan);
    if (!live_send) {
      char detail[192] = {};
      std::snprintf(detail, sizeof(detail),
                    "ac_preview_ok cmd=%s proto=%s supported=%s power=%s "
                    "mode=%s temp_c=%u fan=%s ac_tx_suppressed=true",
                    command_id, spec.protocol, lib_supported ? "true" : "false",
                    spec.power ? "on" : "off", command.mode, spec.temp_c,
                    command.fan);
      publish_event("ac_preview_ready", "info", detail);
      return;
    }
    raw_timing_pending = false;
    preparation.clear();
    irrecv.disableIRIn();
    const bool sent = ac.sendAc();
    irrecv.enableIRIn(true);
    if (!sent) {
      publish_event("command_rejected", "warning", "ac_send_failed");
      return;
    }
    char detail[220] = {};
    std::snprintf(detail, sizeof(detail),
                  "ac_tx_ok cmd=%s proto=%s power=%s mode=%s temp_c=%u fan=%s "
                  "rx_paused=true",
                  command_id, spec.protocol, spec.power ? "on" : "off",
                  command.mode, spec.temp_c, command.fan);
    Serial.printf("ac_command_sent=%s\n", detail);
    publish_event("ac_command_sent", "info", detail);
  }
}

void poll_ir_receiver() {
  static uint16_t last_seen_rawlen = 0;
  static uint32_t last_rawlen_change_ms = 0;
  const uint16_t cur_rawlen = _IRrecv::params.rawlen;
  const uint32_t now_ms = millis();
  if (cur_rawlen != last_seen_rawlen) {
    last_seen_rawlen = cur_rawlen;
    last_rawlen_change_ms = now_ms;
  } else if (cur_rawlen > 0 && _IRrecv::params.rcvstate != 5 &&
             (now_ms - last_rawlen_change_ms) >= 60U) {
    _IRrecv::params.rcvstate = 5;  // kStopState
  }

  if (!irrecv.decode(&ir_results)) {
    raw_timing_pending = false;
    return;
  }
  // decode() has already resumed the live receiver; use only its saved result.
  char captured_session[41] = {};
  if (learning.consume(millis(), captured_session)) {
    const uint32_t capture = sequence + 1U;
    char metadata[513] = {};
    if (xiaoxi::ir::format_learning_capture(ir_results, captured_session, capture,
                                           metadata, sizeof(metadata))) {
      publish_event("ir_learning", "info", metadata);
      raw_timing_pending = true;
      publish_raw_timing_once();
      StaticJsonDocument<JSON_OBJECT_SIZE(3)> complete;
      complete["kind"] = "complete";
      complete["session_id"] = static_cast<const char*>(captured_session);
      complete["capture"] = capture;
      publish_learning(complete);
    } else {
      publish_event("command_rejected", "warning", "capture_metadata_overflow");
    }
  } else {
    expire_learning_state(millis());
    publish_raw_timing_once();
  }
  last_seen_rawlen = 0;
  const String proto_name = typeToString(ir_results.decode_type, ir_results.repeat);
  const bool is_loopback = xiaoxi::ir::matches_loopback_frame(
      proto_name.c_str(), ir_results.value, ir_results.bits);

  char hex_buf[96] = {};
  if (hasACState(ir_results.decode_type)) {
    const uint16_t nbytes = std::min<uint16_t>(ir_results.bits / 8U, 20U);
    size_t pos = 0;
    for (uint16_t i = 0; i < nbytes && pos + 2 < sizeof(hex_buf); ++i) {
      pos += static_cast<size_t>(
          std::snprintf(hex_buf + pos, sizeof(hex_buf) - pos, "%02X",
                        ir_results.state[i]));
    }
  } else {
    std::snprintf(hex_buf, sizeof(hex_buf), "0x%llX",
                  static_cast<unsigned long long>(ir_results.value));
  }

  stdAc::state_t decoded_ac{};
  const bool ac_decoded = IRAcUtils::decodeToState(&ir_results, &decoded_ac);
  char ac_summary[96] = "none";
  if (ac_decoded) {
    std::snprintf(ac_summary, sizeof(ac_summary),
                  "power=%s,mode=%d,temp_c=%.0f,fan=%d",
                  decoded_ac.power ? "on" : "off",
                  static_cast<int>(decoded_ac.mode), decoded_ac.degrees,
                  static_cast<int>(decoded_ac.fanspeed));
  }

  char detail[320] = {};
  std::snprintf(detail, sizeof(detail),
                "rx_ok proto=%s bits=%u rawlen=%u code=%s ac=%s loopback=%s",
                proto_name.c_str(), ir_results.bits, ir_results.rawlen, hex_buf,
                ac_summary, is_loopback ? "true" : "false");
  Serial.printf("ir_rx_frame=%s\n", detail);
  publish_event(is_loopback ? "ir_loopback_verified" : "ir_remote_captured",
                "info", detail);
  irrecv.resume();
}

void maintain_network() {
  const uint32_t now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    mqtt_online = false;
    if (now - last_retry_ms >= retry_backoff_ms) {
      last_retry_ms = now;
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      if (retry_backoff_ms < 30000U) retry_backoff_ms *= 2U;
    }
    return;
  }

  if (mqtt.connected()) {
    mqtt.loop();
    return;
  }

  mqtt_online = false;
  if (now - last_retry_ms < retry_backoff_ms) {
    return;
  }
  last_retry_ms = now;

  if (mqtt.connect("xiaoxi-node02", MQTT_USERNAME, MQTT_PASSWORD, STATUS_TOPIC,
                   1, true, OFFLINE_PAYLOAD)) {
    mqtt.publish(STATUS_TOPIC, ONLINE_PAYLOAD, true);
    mqtt.subscribe(COMMAND_TOPIC);
    mqtt_online = true;
    retry_backoff_ms = 1000;
    Serial.printf("mqtt_connected=true node_id=node02 boot_id=%s\n", boot_id);
  } else {
    Serial.printf("mqtt_connect_failed=true state=%d\n", mqtt.state());
    if (retry_backoff_ms < 30000U) retry_backoff_ms *= 2U;
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  init_boot_id();

  irsend.begin();  // Passive startup: no calibration carrier or NEC self-test.
  irrecv.setUnknownThreshold(12);
  irrecv.setTolerance(kTolerance);
  irrecv.enableIRIn(true);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  tls_client.setCACert(MQTT_CA);
  tls_client.setHandshakeTimeout(5);
  mqtt.setServer(MQTT_HOST, 8883);
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(2);
  mqtt.setBufferSize(3072);  // Bounded 299-entry prepare plus MQTT framing.
  mqtt.setCallback(on_mqtt_message);

  Serial.printf(
      "esp32c3_ir_ready=true node_id=node02 boot_id=%s rx_pin=%u tx_pin=%u "
      "ac_send_supported=true\n",
      boot_id, xiaoxi::ir::IR_RECV_PIN, xiaoxi::ir::IR_SEND_PIN);
}

void loop() {
  expire_learning_state(millis());
  poll_ir_receiver();
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "SET_LOOPBACK" && !learning.armed) {
      run_safe_loopback_test("serial");
    }
  }
  const uint32_t now = millis();
  if (now - last_network_ms >= 100U) {
    last_network_ms = now;
    maintain_network();
  }
  delay(2);
}
