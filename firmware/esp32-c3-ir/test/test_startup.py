"""Execute the actual startup/reconnect functions with offline stand-ins."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


FIRMWARE = Path(__file__).resolve().parents[1]
PRELUDE = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include "ir_node_logic.h"
using byte = unsigned char;
uint32_t now_ms = 0;
uint32_t millis() { return now_ms; }
void delay(unsigned long) {}
constexpr int WL_CONNECTED = 3;
constexpr int WIFI_STA = 1;
constexpr int kTolerance = 25;
constexpr char WIFI_SSID[] = "offline";
constexpr char WIFI_PASSWORD[] = "offline";
constexpr char MQTT_USERNAME[] = "offline";
constexpr char MQTT_PASSWORD[] = "offline";
constexpr char MQTT_CA[] = "offline";
constexpr char MQTT_HOST[] = "offline";
constexpr char STATUS_TOPIC[] = "offline/status";
constexpr char COMMAND_TOPIC[] = "offline/command";
constexpr char ONLINE_PAYLOAD[] = "online";
constexpr char OFFLINE_PAYLOAD[] = "offline";
char boot_id[24] = "node02-00000001";
uint32_t last_retry_ms = 0, retry_backoff_ms = 1000;
bool mqtt_online = false;
int emissions = 0;
struct {
  void begin(int) {}
  template<typename... T> void printf(const char*, T...) {}
} Serial;
void init_boot_id() {}
struct {
  int begin_calls = 0;
  void begin() { ++begin_calls; }
  int calibrate(int) { ++emissions; return 0; }
} irsend;
struct {
  bool enabled = false;
  void setUnknownThreshold(int threshold) { assert(threshold == 12); }
  void setTolerance(int tolerance) { assert(tolerance == kTolerance); }
  void enableIRIn(bool pullup) { assert(pullup); enabled = true; }
} irrecv;
struct {
  int status() { return WL_CONNECTED; }
  void mode(int) {}
  void begin(const char*, const char*) {}
  void disconnect() {}
} WiFi;
struct {
  void setCACert(const char*) {}
  void setHandshakeTimeout(int) {}
} tls_client;
struct {
  bool online = false;
  int loops = 0;
  void setServer(const char*, int) {}
  void setKeepAlive(int) {}
  void setSocketTimeout(int) {}
  void setBufferSize(int size) { assert(size == 3072); }
  void setCallback(void (*)(char*, byte*, unsigned int)) {}
  bool connected() { return online; }
  void loop() { ++loops; }
  bool connect(const char*, const char*, const char*, const char*, int, bool,
               const char*) { online = true; return true; }
  void publish(const char*, const char*, bool) {}
  void subscribe(const char*) {}
  int state() { return 0; }
} mqtt;
void on_mqtt_message(char*, byte*, unsigned int) {}
void run_safe_loopback_test(const char*, bool = false) { ++emissions; }
'''
CHECKS = r'''
int main() {
  setup();
  assert(irsend.begin_calls == 1 && irrecv.enabled && emissions == 0);
  for (now_ms = 0; now_ms < 300000; now_ms += 100) maintain_network();
  assert(mqtt_online && mqtt.loops > 0 && emissions == 0);
  mqtt.online = false;
  now_ms += 30000;
  maintain_network();
  assert(mqtt_online && emissions == 0);
}
'''


class StartupTest(unittest.TestCase):
    def test_boot_idle_and_reconnect_emit_no_ir(self):
        source = (FIRMWARE / "src/main.cpp").read_text()
        network = source[source.index("void maintain_network()"):
                         source.index("}  // namespace")]
        setup = source[source.index("void setup()"):
                       source.index("void loop()")]
        with tempfile.TemporaryDirectory(prefix="xiaoxi-passive-offline-") as tmp:
            harness = Path(tmp) / "startup.cpp"
            binary = Path(tmp) / "startup-test"
            harness.write_text(PRELUDE + network + setup + CHECKS)
            subprocess.run([os.environ.get("CXX", "c++"), "-std=c++17", "-I",
                            str(FIRMWARE / "include"), str(harness), "-o",
                            str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
