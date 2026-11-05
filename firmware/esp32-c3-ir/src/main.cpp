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
#include <cstdio>
#include <cstring>

#include "ir_node_logic.h"
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

char boot_id[24] = {};
uint32_t sequence = 0;
int8_t ir_cal_offset = 0;
uint32_t last_network_ms = 0;
uint32_t last_retry_ms = 0;
uint32_t retry_backoff_ms = 1000;
bool mqtt_online = false;
bool initial_loopback_done = false;
uint32_t initial_loopback_due_ms = 0;

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
  char payload[512] = {};
  const int written = std::snprintf(
      payload, sizeof(payload),
      "{\"schema_version\":\"1.0\",\"node_id\":\"node02\",\"boot_id\":\"%s\","
      "\"sequence\":%lu,\"timestamp\":null,\"simulated\":false,"
      "\"event_type\":\"%s\",\"severity\":\"%s\",\"detail\":\"%s\"}",
      boot_id, static_cast<unsigned long>(sequence++), event_type, severity,
      detail);
  if (written <= 0 || static_cast<size_t>(written) >= sizeof(payload)) {
    return;
  }
  bool sent = false;
  if (mqtt_online && mqtt.connected()) {
    sent = mqtt.publish(EVENT_TOPIC, payload, false);
  }
  Serial.printf("ir_event_transmitted=%s detail=%s\n", sent ? "true" : "false",
                detail);
}

void run_safe_loopback_test(const char* trigger_source) {
  const uint16_t before_rawlen = _IRrecv::params.rawlen;
  const int pin_before = digitalRead(xiaoxi::ir::IR_RECV_PIN);
  Serial.printf("ir_loopback_tx_start=true source=%s pin_tx=%u pin_rx=%u\n",
                trigger_source, xiaoxi::ir::IR_SEND_PIN,
                xiaoxi::ir::IR_RECV_PIN);
  // Keep IRrecv interrupt enabled so GPIO4 captures GPIO3's 38kHz optical burst
  irsend.sendNEC(xiaoxi::ir::LOOPBACK_NEC_CODE, xiaoxi::ir::LOOPBACK_NEC_BITS);
  delay(70);
  const uint16_t after_rawlen = _IRrecv::params.rawlen;
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

bool extract_json_string(const char* json, const char* key, char* out,
                         size_t out_len) {
  char pattern[48] = {};
  std::snprintf(pattern, sizeof(pattern), "\"%s\"", key);
  const char* pos = std::strstr(json, pattern);
  if (!pos) return false;
  pos = std::strchr(pos + std::strlen(pattern), ':');
  if (!pos) return false;
  ++pos;
  while (*pos == ' ' || *pos == '\t') ++pos;
  if (*pos != '"') return false;
  ++pos;
  size_t i = 0;
  while (*pos && *pos != '"' && i + 1 < out_len) {
    if (*pos == '\\' && *(pos + 1)) ++pos;
    out[i++] = *pos++;
  }
  out[i] = '\0';
  return *pos == '"';
}

bool extract_json_int(const char* json, const char* key, int& out) {
  char pattern[48] = {};
  std::snprintf(pattern, sizeof(pattern), "\"%s\"", key);
  const char* pos = std::strstr(json, pattern);
  if (!pos) return false;
  pos = std::strchr(pos + std::strlen(pattern), ':');
  if (!pos) return false;
  ++pos;
  while (*pos == ' ' || *pos == '\t') ++pos;
  char* endptr = nullptr;
  long val = std::strtol(pos, &endptr, 10);
  if (endptr == pos) return false;
  out = static_cast<int>(val);
  return true;
}

bool extract_json_bool(const char* json, const char* key, bool& out) {
  char pattern[48] = {};
  std::snprintf(pattern, sizeof(pattern), "\"%s\"", key);
  const char* pos = std::strstr(json, pattern);
  if (!pos) return false;
  pos = std::strchr(pos + std::strlen(pattern), ':');
  if (!pos) return false;
  ++pos;
  while (*pos == ' ' || *pos == '\t') ++pos;
  if (std::strncmp(pos, "true", 4) == 0) {
    out = true;
    return true;
  }
  if (std::strncmp(pos, "false", 5) == 0) {
    out = false;
    return true;
  }
  return false;
}

void on_mqtt_message(char* topic, byte* payload, unsigned int length) {
  if (!topic || std::strcmp(topic, COMMAND_TOPIC) != 0 || length == 0 ||
      length >= 512) {
    return;
  }
  char buf[512] = {};
  std::memcpy(buf, payload, length);
  buf[length] = '\0';

  char schema[16] = {};
  char node_id[16] = {};
  char command_id[40] = {};
  char action[32] = {};
  int ttl_seconds = 0;

  if (!extract_json_string(buf, "schema_version", schema, sizeof(schema)) ||
      std::strcmp(schema, "1.0") != 0 ||
      !extract_json_string(buf, "node_id", node_id, sizeof(node_id)) ||
      std::strcmp(node_id, "node02") != 0 ||
      !extract_json_string(buf, "command_id", command_id, sizeof(command_id)) ||
      !extract_json_string(buf, "action", action, sizeof(action)) ||
      !extract_json_int(buf, "ttl_seconds", ttl_seconds) ||
      !xiaoxi::ir::is_valid_ttl(ttl_seconds)) {
    publish_event("command_rejected", "warning", "invalid_envelope_or_ttl");
    return;
  }

  if (dedup.seen_or_record(command_id)) {
    publish_event("command_rejected", "warning", "duplicate_command_id");
    return;
  }

  if (std::strcmp(action, "ir_loopback_test") == 0) {
    run_safe_loopback_test(command_id);
    return;
  }

  if (std::strcmp(action, "ac_preview") == 0 ||
      std::strcmp(action, "ac_send") == 0) {
    const bool live_send = (std::strcmp(action, "ac_send") == 0);
    char protocol[24] = {};
    char mode_str[16] = {};
    char fan_str[16] = {};
    bool power = false;
    int temp_c = 26;
    xiaoxi::ir::AcSpec spec{};
    if (!extract_json_string(buf, "protocol", protocol, sizeof(protocol)) ||
        !extract_json_bool(buf, "power", power) ||
        !extract_json_string(buf, "mode", mode_str, sizeof(mode_str)) ||
        !extract_json_int(buf, "temp_c", temp_c) ||
        !extract_json_string(buf, "fan", fan_str, sizeof(fan_str)) ||
        !xiaoxi::ir::validate_ac_spec(protocol, power, mode_str, temp_c,
                                      fan_str, spec)) {
      publish_event("command_rejected", "warning", "invalid_ac_spec");
      return;
    }
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
                    spec.power ? "on" : "off", mode_str, spec.temp_c, fan_str);
      publish_event("ac_preview_ready", "info", detail);
      return;
    }

    irrecv.resume();
    delay(2);
    if (!ac.sendAc()) {
      irrecv.resume();
      publish_event("command_rejected", "warning", "ac_send_failed");
      return;
    }
    delay(70);
    const uint16_t echo_edges = _IRrecv::params.rawlen;
    irrecv.resume();

    char detail[220] = {};
    std::snprintf(detail, sizeof(detail),
                  "ac_tx_ok cmd=%s proto=%s power=%s mode=%s temp_c=%u fan=%s "
                  "rx_echo_edges=%u",
                  command_id, spec.protocol, spec.power ? "on" : "off",
                  mode_str, spec.temp_c, fan_str, echo_edges);
    Serial.printf("ac_command_sent=%s\n", detail);
    publish_event("ac_command_sent", "info", detail);
    return;
  }

  publish_event("command_rejected", "warning", "unsupported_or_disarmed_action");
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
    return;
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
    if (!initial_loopback_done && now >= initial_loopback_due_ms) {
      initial_loopback_done = true;
      run_safe_loopback_test("boot_selftest");
    }
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
    if (!initial_loopback_done) {
      initial_loopback_due_ms = millis() + 800U;
    }
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

  irsend.begin();
  ir_cal_offset = irsend.calibrate(38000);
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
  mqtt.setBufferSize(1024);
  mqtt.setCallback(on_mqtt_message);

  Serial.printf(
      "esp32c3_ir_ready=true node_id=node02 boot_id=%s rx_pin=%u tx_pin=%u "
      "ac_send_supported=true\n",
      boot_id, xiaoxi::ir::IR_RECV_PIN, xiaoxi::ir::IR_SEND_PIN);
}

void loop() {
  poll_ir_receiver();
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "SET_LOOPBACK") {
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
