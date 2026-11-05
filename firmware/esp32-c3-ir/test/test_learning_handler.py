"""Exercise real handler/publisher/receive code with saved library test captures."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_ac_handler import FIRMWARE, LIBRARY, PRELUDE


SUPPORT = r'''
constexpr uint8_t IR_RX_PIN = 4;
int digitalRead(int) { return 1; }
decode_results ir_results{};
uint32_t sequence = 0;
int8_t ir_cal_offset = 0;
bool mqtt_online = true;
constexpr char EVENT_TOPIC[] = "offline/node02/event";
struct {
  std::vector<std::string> payloads;
  bool connected() { return true; }
  bool publish(const char*, const char* payload, bool retained) {
    assert(!retained && std::strlen(payload) < 1024);
    payloads.emplace_back(payload);
    return true;
  }
} mqtt;
'''

CHECKS = r'''
#undef IRac
using Detail = StaticJsonDocument<2048>;
int request_number = 0;
std::string request(const char* action, const std::string& fields = "",
                    const char* fixed_id = nullptr, uint32_t deadline = 0) {
  const std::string id = fixed_id ? fixed_id :
      "request_" + std::to_string(++request_number);
  const std::string identity = std::string(action) == "ir_status" ? "" :
      ",\"boot_id\":\"node02-00000001\",\"deadline_ms\":" +
      std::to_string(deadline ? deadline : now_ms + 10000U);
  const std::string payload = "{\"schema_version\":\"1.0\",\"node_id\":\"node02\","
      "\"command_id\":\"" + id + "\",\"ttl_seconds\":30,\"action\":\"" +
      action + "\"" + identity + fields + "}";
  on_mqtt_message(const_cast<char*>(COMMAND_TOPIC),
      reinterpret_cast<byte*>(const_cast<char*>(payload.data())), payload.size());
  return payload;
}
Detail envelope(size_t index) {
  Detail result;
  assert(!deserializeJson(result, mqtt.payloads.at(index)));
  return result;
}
Detail learning_detail(size_t index) {
  Detail outer = envelope(index);
  assert(outer["detail"].is<const char*>());
  Detail result;
  assert(!deserializeJson(result, outer["detail"].as<const char*>()));
  return result;
}
std::string waveform() {
  std::string result = ",\"frequency_khz\":38,\"timings_us\":[";
  for (int i = 0; i < 15; ++i) result += (i ? ",560" : "9000");
  return result + "]";
}
void start(const char* session = "session_1") {
  request("ir_learn_start", std::string(",\"session_id\":\"") + session +
          "\",\"window_seconds\":2");
  assert(learning_detail(mqtt.payloads.size() - 1)["kind"] == "ready");
  assert(learning.armed);
  mqtt.payloads.clear();
}
void check_capture(decode_results saved, const char* protocol, uint16_t bits,
                   const char* session = "session_1") {
  sequence = UINT32_MAX - 1;
  irrecv.saved = saved;
  irrecv.inject_saved = true;
  raw_timing_pending = false;
  poll_ir_receiver();
  assert(!learning.armed);
  Detail first = learning_detail(0);
  assert(first["kind"] == "capture" && first["session_id"] == session);
  assert(first["capture"].as<uint32_t>() == UINT32_MAX);
  assert(first["protocol"] == protocol && first["bits"] == bits);
  const size_t chunks = (saved.rawlen + 15U) / 16;
  assert(chunks <= 19);
  for (size_t i = 0; i < chunks; ++i) {
    Detail chunk = envelope(i + 1);
    assert(chunk["event_type"] == "ir_raw_timing");
    assert(chunk["sequence"].as<uint32_t>() == UINT32_MAX + uint32_t(i));
    const std::string text = chunk["detail"].as<const char*>();
    assert(text.find("capture=4294967295 ") != std::string::npos);
    assert(text.find("rawlen=" + std::to_string(saved.rawlen)) != std::string::npos);
    assert(text.find("kept=" + std::to_string(saved.rawlen)) != std::string::npos);
    if (!i) assert(text.find("times=2,") != std::string::npos);
  }
  Detail last = learning_detail(chunks + 1);
  assert(last["kind"] == "complete" && last["session_id"] == session);
  assert(last["capture"].as<uint32_t>() == UINT32_MAX);
  assert(mqtt.payloads.size() == chunks + 3);  // Existing final IR diagnostic.
}
int main() {
  request("ir_status");
  auto status = learning_detail(0);
  assert(status["kind"] == "status" && status["version"] == "learn1");
  assert(status["uptime_ms"] == now_ms && status["command_id"] == "request_1");
  assert(ac.calls == 0 && irsend.raw_calls == 0 && irrecv.disabled == 0);
  mqtt.payloads.clear();

  request("ir_raw_prepare", waveform());
  assert(preparation.pending && irsend.raw_calls == 0);
  const std::string old_challenge = learning_detail(0)["challenge"].as<const char*>();
  assert(old_challenge.size() == 32);
  mqtt.payloads.clear();
  _IRrecv::params.rawlen = 20;
  start();
  assert(!preparation.pending && _IRrecv::params.rawlen == 0);
  assert(irrecv.disabled == 1 && irrecv.enabled);
  request("ir_raw_prepare", waveform());
  assert(envelope(0)["detail"] == "learning_busy" && irsend.raw_calls == 0);
  mqtt.payloads.clear();

  IRKelvinatorAC kelvinator(3);
  kelvinator.setPower(true);
  kelvinator.setMode(kKelvinatorCool);
  kelvinator.setTemp(26);
  kelvinator.setQuiet(true);
  kelvinator.setIonFilter(true);
  kelvinator.send(0);
  kelvinator._irsend.makeDecodeResult();
  assert(irrecv.decode(&kelvinator._irsend.capture));
  assert(kelvinator._irsend.capture.decode_type == KELVINATOR);
  check_capture(kelvinator._irsend.capture, "KELVINATOR", 128);
  auto state = learning_detail(0);
  assert(state["state"]["power"] == true && state["state"]["temp_c"] == 26);
  assert(state["state"]["quiet"] == true && state["state"]["filter"] == true);
  assert(state["state"]["econo"].isNull() && state["state"]["sleep"].isNull());
  assert(state["state"]["ifeel"].isNull() && state["state"].size() == 14);
  for (const auto& payload : mqtt.payloads) std::puts(payload.c_str());
  mqtt.payloads.clear();

  // The same saved result cannot consume the completed arm a second time.
  irrecv.saved = kelvinator._irsend.capture;
  irrecv.inject_saved = true;
  poll_ir_receiver();
  assert(mqtt.payloads.size() == 1 && envelope(0)["event_type"] == "ir_remote_captured");
  mqtt.payloads.clear();

  start("gree_subset");
  IRGreeAC gree(3);
  gree.setPower(true);
  gree.setMode(kGreeCool);
  gree.setTemp(25);
  gree.setEcono(true);
  gree.send(0);
  gree._irsend.makeDecodeResult();
  uint16_t full_raw[300];
  const auto original = gree._irsend.capture;
  assert(original.rawlen < 270);
  for (size_t i = 0; i < original.rawlen; ++i) full_raw[i] = original.rawbuf[i];
  for (size_t i = original.rawlen; i < 280; ++i) full_raw[i] = 10000;
  decode_results subset{};
  subset.rawbuf = full_raw;
  subset.rawlen = 280;
  assert(irrecv.decode(&subset));
  assert(subset.decode_type == GREE && subset.bits == 64);
  check_capture(subset, "GREE", 64, "gree_subset");
  auto gree_state = learning_detail(0);
  assert(gree_state["state"]["quiet"].isNull());
  assert(gree_state["state"]["filter"].isNull());
  assert(gree_state["state"]["econo"] == true);
  for (const auto& payload : mqtt.payloads) std::puts(payload.c_str());
  mqtt.payloads.clear();

  start("unknown");
  auto unknown = subset;
  unknown.decode_type = UNKNOWN;
  unknown.bits = 32;
  check_capture(unknown, "UNKNOWN", 32, "unknown");
  assert(learning_detail(0)["state"].isNull());
  mqtt.payloads.clear();

  start("cancel_me");
  request("ir_learn_cancel", ",\"session_id\":\"foreign\"");
  assert(learning.armed && envelope(0)["detail"] == "no_matching_learning_session");
  mqtt.payloads.clear();
  request("ir_learn_cancel", ",\"session_id\":\"cancel_me\"");
  assert(!learning.armed && learning_detail(0)["kind"] == "cancelled");
  mqtt.payloads.clear();
  start("expire_me");
  now_ms += 2000;
  expire_learning_state(now_ms);
  assert(!learning.armed && learning_detail(0)["kind"] == "expired");
  expire_learning_state(now_ms + 1);
  assert(mqtt.payloads.size() == 1);
  mqtt.payloads.clear();

  request("ir_raw_prepare", waveform());
  assert(irsend.raw_calls == 0 && preparation.pending);
  const std::string challenge = learning_detail(0)["challenge"].as<const char*>();
  assert(challenge != old_challenge);
  assert(learning_detail(0)["expires_ms"].as<uint32_t>() == now_ms + 10000);
  mqtt.payloads.clear();
  const auto commit = request("ir_raw_commit", ",\"challenge\":\"" + challenge + "\"",
                               "commit_once");
  assert(irsend.raw_calls == 1 && !preparation.pending && irrecv.enabled);
  assert(irsend.raw_sent.size() == 15 && irsend.raw_sent[0] == 9000);
  assert(sending_waveform.count == 0 && learning_detail(0)["kind"] == "sent");
  mqtt.payloads.clear();
  on_mqtt_message(const_cast<char*>(COMMAND_TOPIC),
      reinterpret_cast<byte*>(const_cast<char*>(commit.data())), commit.size());
  assert(irsend.raw_calls == 1 && envelope(0)["detail"] == "duplicate_command_id");
  mqtt.payloads.clear();
  request("ir_raw_commit", ",\"challenge\":\"" + challenge + "\"");
  assert(irsend.raw_calls == 1 && envelope(0)["detail"] == "invalid_or_expired_challenge");
  mqtt.payloads.clear();
  request("ir_raw_prepare", waveform());
  const std::string expiring = learning_detail(0)["challenge"].as<const char*>();
  mqtt.payloads.clear();
  now_ms += 10000;
  request("ir_raw_commit", ",\"challenge\":\"" + expiring + "\"");
  assert(irsend.raw_calls == 1 && !preparation.pending);
  assert(envelope(0)["detail"] == "invalid_or_expired_challenge");
  mqtt.payloads.clear();
  request("ir_raw_prepare", waveform(), nullptr, now_ms);
  assert(!preparation.pending && irsend.raw_calls == 1);
  assert(envelope(0)["detail"] == "invalid_command_or_deadline");
  std::puts("learning/replay behavioral checks PASS");
}
'''


class LearningHandlerTest(unittest.TestCase):
    def test_saved_capture_contract_and_single_replay(self):
        source = (FIRMWARE / "src/main.cpp").read_text()
        implementation = source[source.index("void publish_event("):
                                source.index("void maintain_network()")]
        prelude = PRELUDE[:PRELUDE.index("void publish_event(")] + "\n#define IRac TrackedAc\n"
        with tempfile.TemporaryDirectory(prefix="xiaoxi-learning-offline-") as tmp:
            harness = Path(tmp) / "learning.cpp"
            harness.write_text(prelude + SUPPORT + implementation + CHECKS)
            binary = Path(tmp) / "learning-test"
            command = [os.environ.get("CXX", "c++"), "-std=c++17", "-DUNIT_TEST",
                       "-D_IR_ENABLE_DEFAULT_=false", "-DSEND_RAW=true"]
            for protocol in ("KELVINATOR", "GREE", "NEC"):
                command += [f"-DSEND_{protocol}=true", f"-DDECODE_{protocol}=true"]
            for path in (FIRMWARE / "include", LIBRARY / "src", LIBRARY / "test",
                         FIRMWARE / ".pio/libdeps/native/ArduinoJson/src"):
                command += ["-I", str(path)]
            command += [str(harness)]
            for name in ("IRac", "IRrecv", "IRsend", "IRtimer", "IRutils", "IRtext",
                         "ir_Kelvinator", "ir_Gree", "ir_NEC"):
                command.append(str(LIBRARY / "src" / f"{name}.cpp"))
            command += ["-o", str(binary)]
            subprocess.run(command, check=True, timeout=60)
            result = subprocess.run([str(binary)], check=False, timeout=10,
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("behavioral checks PASS", result.stdout)
        events = [json.loads(line) for line in result.stdout.splitlines()
                  if line.startswith("{")]
        captures = [json.loads(event["detail"]) for event in events
                    if event["event_type"] == "ir_learning" and
                    json.loads(event["detail"])["kind"] == "capture"]
        self.assertEqual([(x["protocol"], x["bits"]) for x in captures],
                         [("KELVINATOR", 128), ("GREE", 64)])


if __name__ == "__main__":
    unittest.main()
