"""Compile the actual MQTT handler with IRremoteESP8266's offline test backend."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


FIRMWARE = Path(__file__).resolve().parents[1]
LIBRARY = Path(os.environ.get(
    "IRREMOTEESP8266_DIR", FIRMWARE / ".pio/libdeps/esp32c3/IRremoteESP8266"
))

PRELUDE = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include "IRac.h"
#include "IRsend_test.h"
#include "IRutils.h"
#include "ir_node_logic.h"

using byte = unsigned char;
namespace _IRrecv { extern atomic_irparams_t params; }
struct { template<typename... Args> void printf(const char*, Args...) {} } Serial;
void delay(unsigned long) {}

struct TrackedAc : IRac {
  TrackedAc() : IRac(3) {}
  int calls = 0;
  bool fail = false;
  stdAc::state_t sent;
  bool sendAc() {
    ++calls;
    sent = next;
    return !fail && IRac::sendAc();
  }
} ac;
IRsendTest irsend(3);
IRrecv irrecv(4);  // No save buffer: decode the synthetic capture directly.
xiaoxi::ir::CommandDeduplicator dedup;
constexpr char COMMAND_TOPIC[] = "xiaoxi/dorm/node02/command";
std::string event_type, event_detail;
int successes = 0;
void publish_event(const char* type, const char*, const char* detail) {
  event_type = type;
  event_detail = detail;
  if (event_type == "ac_preview_ready" || event_type == "ac_command_sent") {
    ++successes;
  }
}
void run_safe_loopback_test(const char*) {
  irsend.sendNEC(xiaoxi::ir::LOOPBACK_NEC_CODE);
}
#define IRac TrackedAc
'''

CHECKS = r'''
#undef IRac
void request(const char* action, const char* protocol = "KELVINATOR",
             bool power = true, const char* mode = "cool", int temp = 26,
             const char* fan = "auto") {
  dedup = xiaoxi::ir::CommandDeduplicator{};
  event_type.clear();
  event_detail.clear();
  successes = 0;
  ac.calls = 0;
  irsend.reset();
  char payload[512];
  std::snprintf(payload, sizeof(payload),
      "{\"schema_version\":\"1.0\",\"node_id\":\"node02\","
      "\"command_id\":\"offline-test\",\"ttl_seconds\":30,"
      "\"action\":\"%s\",\"protocol\":\"%s\",\"power\":%s,"
      "\"mode\":\"%s\",\"temp_c\":%d,\"fan\":\"%s\"}",
      action, protocol, power ? "true" : "false", mode, temp, fan);
  on_mqtt_message(const_cast<char*>(COMMAND_TOPIC),
                  reinterpret_cast<byte*>(payload), std::strlen(payload));
}

int main() {
  request("ac_preview");
  assert(ac.calls == 0 && irsend.outputStr().empty());
  assert(event_type == "ac_preview_ready");

  // Unspecified options must not leak from an earlier command/state.
  ac.next.model = 2;
  ac.next.swingv = stdAc::swingv_t::kAuto;
  ac.next.swingh = stdAc::swingh_t::kAuto;
  ac.next.quiet = ac.next.turbo = ac.next.econo = ac.next.light = true;
  ac.next.filter = ac.next.clean = ac.next.beep = ac.next.iFeel = true;
  ac.next.sleep = ac.next.clock = 42;
  ac.next.command = stdAc::ac_command_t::kTimerCommand;
  ac.next.sensorTemperature = 31;
  request("ac_send");
  assert(ac.calls == 1 && irsend.outputStr().empty());
  assert(event_type == "ac_command_sent");
  assert(ac.sent.protocol == KELVINATOR && ac.sent.power);
  assert(ac.sent.mode == stdAc::opmode_t::kCool && ac.sent.degrees == 26);
  assert(ac.sent.celsius && ac.sent.fanspeed == stdAc::fanspeed_t::kAuto);
  assert(ac.sent.model == -1 && ac.sent.swingv == stdAc::swingv_t::kOff);
  assert(ac.sent.swingh == stdAc::swingh_t::kOff);
  assert(!ac.sent.quiet && !ac.sent.turbo && !ac.sent.econo && !ac.sent.light);
  assert(!ac.sent.filter && !ac.sent.clean && !ac.sent.beep && !ac.sent.iFeel);
  assert(ac.sent.sleep == -1 && ac.sent.clock == -1);
  assert(ac.sent.command == stdAc::ac_command_t::kControlCommand);
  assert(ac.sent.sensorTemperature == kNoTempValue);

  // Encode/decode the selected cool/26/auto state with the installed library.
  IRKelvinatorAC encoder(3);
  ac.kelvinator(&encoder, ac.sent.power, ac.sent.mode, ac.sent.degrees,
      ac.sent.fanspeed, ac.sent.swingv, ac.sent.swingh, ac.sent.quiet,
      ac.sent.turbo, ac.sent.light, ac.sent.filter, ac.sent.clean);
  encoder._irsend.makeDecodeResult();
  assert(irrecv.decode(&encoder._irsend.capture));
  assert(encoder._irsend.capture.decode_type == KELVINATOR);
  stdAc::state_t decoded;
  assert(IRAcUtils::decodeToState(&encoder._irsend.capture, &decoded));
  assert(decoded.power && decoded.mode == stdAc::opmode_t::kCool);
  assert(decoded.degrees == 26 && decoded.fanspeed == stdAc::fanspeed_t::kAuto);

  request("ac_send", "GREE", false, "heat", 23, "high");
  assert(ac.calls == 1 && irsend.outputStr().empty());
  assert(event_type == "ac_command_sent");
  assert(ac.sent.protocol == GREE && !ac.sent.power);
  assert(ac.sent.mode == stdAc::opmode_t::kHeat && ac.sent.degrees == 23);
  assert(ac.sent.fanspeed == stdAc::fanspeed_t::kHigh);

  // MIDEA is allowed by the parser but deliberately disabled in this test build.
  for (const char* action : {"ac_preview", "ac_send"}) {
    request(action, "MIDEA");
    assert(ac.calls == 0 && irsend.outputStr().empty());
    assert(event_type == "command_rejected" && successes == 0);
    assert(event_detail == "unsupported_ac_protocol");
  }
  ac.fail = true;
  request("ac_send");
  assert(ac.calls == 1 && irsend.outputStr().empty());
  assert(event_type == "command_rejected" && successes == 0);
  assert(event_detail == "ac_send_failed");
  std::puts("AC handler: dry-run, single send, cool26 roundtrip, off, rejection PASS");
}
'''


class AcHandlerTest(unittest.TestCase):
    def test_actual_handler_and_library_encoder(self):
        source = (FIRMWARE / "src/main.cpp").read_text()
        handler = source[source.index("stdAc::opmode_t to_stdac_mode("):
                         source.index("void poll_ir_receiver()")]
        sources = ["IRac", "IRrecv", "IRsend", "IRtimer", "IRutils", "IRtext",
                   "ir_Kelvinator", "ir_Gree", "ir_NEC"]
        with tempfile.TemporaryDirectory(prefix="xiaoxi-ac-offline-") as tmp:
            harness = Path(tmp) / "handler.cpp"
            harness.write_text(PRELUDE + handler + CHECKS)
            binary = Path(tmp) / "handler-test"
            command = [os.environ.get("CXX", "c++"), "-std=c++17", "-DUNIT_TEST",
                       "-D_IR_ENABLE_DEFAULT_=false"]
            for protocol in ("KELVINATOR", "GREE", "NEC"):
                command += [f"-DSEND_{protocol}=true", f"-DDECODE_{protocol}=true"]
            for path in (FIRMWARE / "include", LIBRARY / "src", LIBRARY / "test"):
                command += ["-I", str(path)]
            command += [str(harness)]
            command += [str(LIBRARY / "src" / f"{name}.cpp") for name in sources]
            command += ["-o", str(binary)]
            subprocess.run(command, check=True, timeout=60)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
