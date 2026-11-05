"""Exercise the actual timing publisher with in-memory GPIO/MQTT stand-ins."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

FIRMWARE = Path(__file__).resolve().parents[1]
PRELUDE = r'''
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include "ir_node_logic.h"
#include "ir_raw_timing.h"
#include "ir_learning.h"
struct { template<typename... Args> void printf(const char*, Args...) {} } Serial;
void delay(unsigned long) {}
int digitalRead(int) { return 1; }
namespace _IRrecv { struct { uint16_t rawlen = 0; uint8_t rcvstate = 0; } params; }
struct { const uint16_t* rawbuf; uint16_t rawlen; bool overflow; } ir_results;
struct {
  int calls = 0;
  uint16_t received = 68;
  void sendNEC(uint64_t, uint16_t) { ++calls; _IRrecv::params.rawlen = received; }
} irsend;
struct {
  bool online = true;
  std::vector<std::string> payloads;
  bool connected() { return online; }
  bool publish(const char*, const char* payload, bool retained) {
    assert(!retained);
    assert(std::strlen(payload) < 1024);
    payloads.emplace_back(payload);
    return true;
  }
} mqtt;
constexpr char EVENT_TOPIC[] = "offline/node02/event";
char boot_id[] = "node02-00000012";
uint32_t sequence = 0;
int8_t ir_cal_offset = -3;
bool mqtt_online = true;
bool raw_timing_pending = false;
'''
CHECKS = r'''
int main() {
  uint16_t saved[300];
  std::fill_n(saved, 300, 65535);
  ir_results = {saved, 68, false};
  publish_raw_timing_once();
  assert(mqtt.payloads.empty());
  // An externally supplied command id must not select internal boot capture.
  run_safe_loopback_test("boot_selftest");
  assert(!raw_timing_pending && irsend.calls == 1);
  mqtt.payloads.clear();
  run_safe_loopback_test("boot_selftest", true);
  assert(raw_timing_pending && irsend.calls == 2);
  // The live receiver was cleared during decode; saved data must survive.
  _IRrecv::params.rawlen = 0;
  publish_raw_timing_once();
  assert(!raw_timing_pending && mqtt.payloads.size() == 6);
  const auto count = mqtt.payloads.size();
  publish_raw_timing_once();
  assert(mqtt.payloads.size() == count && irsend.calls == 2);
  for (const auto& payload : mqtt.payloads) std::puts(payload.c_str());
  mqtt.payloads.clear();
  sequence = UINT32_MAX;
  raw_timing_pending = true;
  ir_results = {saved, 65535, true};
  publish_raw_timing_once();
  assert(mqtt.payloads.size() == 19 && sequence == 18);
  for (const auto& payload : mqtt.payloads) std::puts(payload.c_str());
  mqtt.payloads.clear();
  mqtt.online = false;
  raw_timing_pending = true;
  publish_raw_timing_once();
  assert(!raw_timing_pending && mqtt.payloads.empty());
  irsend.received = 0;
  run_safe_loopback_test("boot_selftest", true);
  assert(!raw_timing_pending && irsend.calls == 3);
}
'''


class RawPublisherTest(unittest.TestCase):
    def test_actual_bounded_nonretained_publisher(self):
        source = (FIRMWARE / "src/main.cpp").read_text()
        publisher = source[source.index("void publish_event("):
                           source.index("stdAc::opmode_t to_stdac_mode(")]
        with tempfile.TemporaryDirectory(prefix="xiaoxi-raw-offline-") as tmp:
            harness = Path(tmp) / "publisher.cpp"
            binary = Path(tmp) / "publisher"
            harness.write_text(PRELUDE + publisher + CHECKS)
            subprocess.run([os.environ.get("CXX", "c++"), "-std=c++17",
                            "-I", str(FIRMWARE / "include"),
                            "-I", str(FIRMWARE / ".pio/libdeps/native/ArduinoJson/src"),
                            str(harness),
                            "-o", str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], check=True, timeout=10,
                                    text=True, capture_output=True)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(events[0]["event_type"], "ir_loopback_diag")
        raw = events[1:6]
        self.assertEqual(len(raw), 5)
        for index, event in enumerate(raw):
            self.assertEqual(event["event_type"], "ir_raw_timing")
            self.assertIs(event["simulated"], False)  # Real publisher; inputs are synthetic.
            self.assertEqual(event["sequence"], 2 + index)
            self.assertIn("capture=2 rawlen=68 kept=68 truncated=0 overflow=0",
                          event["detail"])
            self.assertIn(f"offset={index * 16} ", event["detail"])
            self.assertIn("times=2,131070" if index == 0 else "times=131070",
                          event["detail"])
        for index, event in enumerate(events[6:]):
            self.assertEqual(event["sequence"], (2**32 - 1 + index) % 2**32)
            self.assertIn("kept=300 truncated=1 overflow=1", event["detail"])
        # Raw chunks precede the normal event and its existing final cleanup.
        poll = source[source.index("void poll_ir_receiver()"):
                      source.index("void maintain_network()")]
        self.assertLess(poll.index("publish_raw_timing_once();"),
                        poll.index('publish_event(is_loopback'))


if __name__ == "__main__":
    unittest.main()
