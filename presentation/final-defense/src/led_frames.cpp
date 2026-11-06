// Export the real firmware renderer; this program never connects to a board.
#include <iostream>
#include <string>
#include "../../../firmware/arduino-uno-r4/include/led_companion.h"
using namespace xiaoxi::led;

int main() {
  const char* keys[] = {"happy", "temperature", "humidity", "light", "sleepy",
                        "hot", "cry", "connecting", "voice"};
  std::cout << "{\"width\":12,\"height\":8,\"step_ms\":100,\"states\":{";
  for (int k = 0; k < 9; ++k) {
    if (k) std::cout << ',';
    std::cout << '"' << keys[k] << "\":[";
    const int count = k == 8 ? 9 : 60;
    for (int f = 0; f < count; ++f) {
      if (f) std::cout << ',';
      CompanionInput in(true, true, true, 24.0f, 55.0f, 0.46f, false);
      if (k >= 1 && k <= 4) in.manual_scene_offset = k;
      if (k == 4) in.light_ratio = 0.04f;
      if (k == 5) in.temperature_c = 30.0f;
      if (k == 6) in.sht_ok = false;
      if (k == 7) in.network_ready = false;
      if (k == 8) in.voice_mode = true;
      uint32_t words[3];
      const auto scene = render_companion_frame(in, f * 100, words);
      std::cout << "{\"scene\":" << static_cast<int>(scene) << ",\"rows\":[";
      for (int r = 0; r < 8; ++r) {
        if (r) std::cout << ',';
        std::cout << '"';
        for (int c = 0; c < 12; ++c) std::cout << (get_pixel_12x8(words, r, c) ? '1' : '0');
        std::cout << '"';
      }
      std::cout << "]}";
    }
    std::cout << ']';
  }
  std::cout << "}}\n";
}
