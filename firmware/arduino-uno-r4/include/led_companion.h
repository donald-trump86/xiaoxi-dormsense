#ifndef XIAOXI_LED_COMPANION_H
#define XIAOXI_LED_COMPANION_H

#include <math.h>
#include <stddef.h>
#include <stdint.h>

namespace xiaoxi {
namespace led {

enum SceneKind : uint8_t {
  SCENE_ALERT_CRY = 0,
  SCENE_CONNECTING = 1,
  SCENE_FACE_HAPPY = 2,
  SCENE_FACE_SLEEPY = 3,
  SCENE_FACE_HOT = 4,
  SCENE_THERMOMETER = 5,
  SCENE_DROPLET = 6,
  SCENE_LIGHTBULB = 7,
  SCENE_VOICE_WAVE = 8
};

enum ButtonGesture : uint8_t {
  BUTTON_GESTURE_NONE = 0,
  BUTTON_GESTURE_SINGLE_PRESS = 1,
  BUTTON_GESTURE_DOUBLE_PRESS = 2,
  BUTTON_GESTURE_LONG_PRESS = 3,
  BUTTON_GESTURE_LONG_RELEASE = 4
};

struct ButtonGestureTracker {
  uint8_t baseline_mask = 0x3Fu;
  uint8_t last_seen_mask = 0x3Fu;
  bool initialized = false;
  bool raw_active = false;
  bool debounced_active = false;
  bool long_fired = false;
  uint8_t pending_clicks = 0;
  uint8_t last_changed_mask = 0;
  uint32_t last_raw_change_ms = 0;
  uint32_t mask_stable_since_ms = 0;
  uint32_t press_started_ms = 0;
  uint32_t last_release_ms = 0;

  static constexpr uint32_t kDebounceMs = 30UL;
  static constexpr uint32_t kLongPressMs = 700UL;
  static constexpr uint32_t kDoubleClickWindowMs = 380UL;
  static constexpr uint32_t kAutoRebaselineMs = 4000UL;

  void init(uint8_t resting_mask, uint32_t now_ms = 0) {
    baseline_mask = static_cast<uint8_t>(resting_mask & 0x3Fu);
    last_seen_mask = baseline_mask;
    initialized = true;
    raw_active = false;
    debounced_active = false;
    long_fired = false;
    pending_clicks = 0;
    last_changed_mask = 0;
    mask_stable_since_ms = now_ms;
  }

  ButtonGesture update(uint8_t current_mask, uint32_t now_ms) {
    current_mask = static_cast<uint8_t>(current_mask & 0x3Fu);
    if (!initialized) {
      init(current_mask, now_ms);
      return BUTTON_GESTURE_NONE;
    }
    if (current_mask != last_seen_mask) {
      last_seen_mask = current_mask;
      mask_stable_since_ms = now_ms;
    } else if (!long_fired && current_mask != baseline_mask &&
               (now_ms - mask_stable_since_ms) >= kAutoRebaselineMs) {
      // Adopt a new steady mask after >= 4s (e.g. hot-plugged wire or divider
      // settling), but preserve the resting baseline during a recognized long press.
      init(current_mask, now_ms);
      return BUTTON_GESTURE_NONE;
    }

    const uint8_t diff = static_cast<uint8_t>((current_mask ^ baseline_mask) & 0x3Fu);
    const bool active_now = (diff != 0);
    if (active_now != raw_active) {
      raw_active = active_now;
      last_raw_change_ms = now_ms;
    }
    if (active_now) {
      last_changed_mask = diff;
    }

    if ((now_ms - last_raw_change_ms) >= kDebounceMs &&
        debounced_active != raw_active) {
      debounced_active = raw_active;
      if (debounced_active) {
        press_started_ms = now_ms;
        long_fired = false;
      } else {
        if (!long_fired) {
          ++pending_clicks;
          last_release_ms = now_ms;
          if (pending_clicks >= 2) {
            pending_clicks = 0;
            return BUTTON_GESTURE_DOUBLE_PRESS;
          }
        } else {
          long_fired = false;
          return BUTTON_GESTURE_LONG_RELEASE;
        }
      }
    }

    if (debounced_active && !long_fired &&
        (now_ms - press_started_ms) >= kLongPressMs) {
      long_fired = true;
      pending_clicks = 0;
      return BUTTON_GESTURE_LONG_PRESS;
    }

    if (!debounced_active && pending_clicks == 1 &&
        (now_ms - last_release_ms) >= kDoubleClickWindowMs) {
      pending_clicks = 0;
      return BUTTON_GESTURE_SINGLE_PRESS;
    }

    return BUTTON_GESTURE_NONE;
  }
};

struct CompanionInput {
  bool network_ready;
  bool sht_ok;
  bool light_ok;
  float temperature_c;
  float humidity_pct;
  float light_ratio;
  bool publish_flash;
  bool voice_mode;
  uint8_t manual_scene_offset;

  CompanionInput(bool net, bool sht, bool light, float temp, float hum,
                 float lratio, bool flash, bool voice = false,
                 uint8_t offset = 0)
      : network_ready(net),
        sht_ok(sht),
        light_ok(light),
        temperature_c(temp),
        humidity_pct(hum),
        light_ratio(lratio),
        publish_flash(flash),
        voice_mode(voice),
        manual_scene_offset(offset) {}
};

inline void pack_rows_12x8(const uint16_t rows[8], uint32_t out_words[3]) {
  out_words[0] = 0;
  out_words[1] = 0;
  out_words[2] = 0;
  for (uint8_t r = 0; r < 8; ++r) {
    const uint16_t row_bits = static_cast<uint16_t>(rows[r] & 0x0FFFu);
    for (uint8_t c = 0; c < 12; ++c) {
      if ((row_bits & (1u << (11 - c))) != 0) {
        const uint8_t idx = static_cast<uint8_t>(r * 12 + c);
        out_words[idx / 32] |= (1UL << (31 - (idx % 32)));
      }
    }
  }
}

inline bool get_pixel_12x8(const uint32_t words[3], uint8_t r, uint8_t c) {
  if (r >= 8 || c >= 12) {
    return false;
  }
  const uint8_t idx = static_cast<uint8_t>(r * 12 + c);
  return (words[idx / 32] & (1UL << (31 - (idx % 32)))) != 0;
}

inline const uint8_t* digit_3x5(uint8_t d) {
  static const uint8_t kDigits[10][5] = {
      {0b111, 0b101, 0b101, 0b101, 0b111},  // 0
      {0b010, 0b110, 0b010, 0b010, 0b111},  // 1
      {0b111, 0b001, 0b111, 0b100, 0b111},  // 2
      {0b111, 0b001, 0b111, 0b001, 0b111},  // 3
      {0b101, 0b101, 0b111, 0b001, 0b001},  // 4
      {0b111, 0b100, 0b111, 0b001, 0b111},  // 5
      {0b111, 0b100, 0b111, 0b101, 0b111},  // 6
      {0b111, 0b001, 0b001, 0b001, 0b001},  // 7
      {0b111, 0b101, 0b111, 0b101, 0b111},  // 8
      {0b111, 0b101, 0b111, 0b001, 0b111},  // 9
  };
  return kDigits[d % 10];
}

inline void draw_two_digits(uint16_t rows[8], int value) {
  if (value < 0) {
    value = 0;
  } else if (value > 99) {
    value = 99;
  }
  const uint8_t tens = static_cast<uint8_t>((value / 10) % 10);
  const uint8_t ones = static_cast<uint8_t>(value % 10);
  const uint8_t* g_tens = digit_3x5(tens);
  const uint8_t* g_ones = digit_3x5(ones);

  // Tens at cols 5..7 (bits 6..4), Ones at cols 9..11 (bits 2..0), rows 2..6
  for (uint8_t i = 0; i < 5; ++i) {
    const uint16_t t_bits = static_cast<uint16_t>(g_tens[i] & 0x7u) << 4;
    const uint16_t o_bits = static_cast<uint16_t>(g_ones[i] & 0x7u);
    rows[2 + i] = static_cast<uint16_t>((rows[2 + i] & 0xFF80u) | t_bits | o_bits);
  }
}

constexpr uint32_t kSceneDurationMs = 6000UL;
constexpr uint32_t kPhaseDurationMs = 1000UL;

inline SceneKind select_scene(const CompanionInput& in, uint32_t now_ms) {
  if (in.voice_mode) {
    return SCENE_VOICE_WAVE;
  }
  if (!in.sht_ok || !in.light_ok) {
    return SCENE_ALERT_CRY;
  }
  if (!in.network_ready) {
    return SCENE_CONNECTING;
  }
  const uint32_t slot_count = (in.light_ratio < 0.10f) ? 5UL : 4UL;
  const uint8_t slot = static_cast<uint8_t>(
      ((now_ms / kSceneDurationMs) + in.manual_scene_offset) % slot_count);
  if (slot == 0) {
    if (in.temperature_c >= 29.0f || in.humidity_pct >= 75.0f) {
      return SCENE_FACE_HOT;
    }
    return SCENE_FACE_HAPPY;
  }
  if (slot == 1) {
    return SCENE_THERMOMETER;
  }
  if (slot == 2) {
    return SCENE_DROPLET;
  }
  if (slot == 3) {
    return SCENE_LIGHTBULB;
  }
  return SCENE_FACE_SLEEPY;
}

inline SceneKind render_companion_frame(
    const CompanionInput& in, uint32_t now_ms, uint32_t out_words[3]) {
  const SceneKind scene = select_scene(in, now_ms);
  const uint8_t phase = static_cast<uint8_t>((now_ms / kPhaseDurationMs) % 6UL);
  uint16_t rows[8] = {0, 0, 0, 0, 0, 0, 0, 0};

  switch (scene) {
    case SCENE_ALERT_CRY: {
      // Crying face with slow falling teardrops
      const bool tear_low = (phase % 2) == 1;
      rows[0] = 0b001100001100;
      rows[1] = 0b001100001100;
      rows[2] = tear_low ? 0b000000000000 : 0b010000000010;
      rows[3] = tear_low ? 0b010000000010 : 0b000000000000;
      rows[4] = 0b000011110000;
      rows[5] = 0b000100001000;
      rows[6] = 0b001000000100;
      rows[7] = tear_low ? 0b010000000010 : 0b000000000000;
      break;
    }
    case SCENE_CONNECTING: {
      // Searching eyes + slow expanding Wi-Fi wave on right
      const uint8_t wave = static_cast<uint8_t>(phase % 3);
      rows[1] = (phase < 3) ? 0b011001100000 : 0b001100110000;
      rows[2] = (phase < 3) ? 0b011001100000 : 0b001100110000;
      rows[5] = 0b001111000000;
      if (wave >= 0) {
        rows[6] |= 0b000000000010;
      }
      if (wave >= 1) {
        rows[4] |= 0b000000000101;
        rows[5] |= 0b000000000010;
      }
      if (wave >= 2) {
        rows[2] |= 0b000000001110;
        rows[3] |= 0b000000010001;
      }
      break;
    }
    case SCENE_FACE_SLEEPY: {
      // Closed eyes (- -) with slow floating Zzz in top-right
      const uint8_t z_step = static_cast<uint8_t>((phase / 2) % 3);
      rows[0] = (z_step >= 2) ? 0b000000000111 : 0b000000000000;
      rows[1] = (z_step >= 2) ? 0b000000000010 : ((z_step == 1) ? 0b000000001100 : 0);
      rows[2] = (z_step >= 2) ? 0b000000000111 : ((z_step == 1) ? 0b000000000100 : 0);
      rows[3] = 0b001110011100;
      rows[5] = (z_step == 1) ? 0b000010010000 : 0b000001100000;
      rows[6] = 0b000001100000;
      break;
    }
    case SCENE_FACE_HOT: {
      // Sweating face with slow sweat drop on right temple
      const bool drop_down = (phase >= 3);
      rows[0] = drop_down ? 0b000000000000 : 0b000000000010;
      rows[1] = 0b001100011000 | 0b000000000011;
      rows[2] = 0b001100011000 | (drop_down ? 0b000000000011 : 0b000000000000);
      rows[5] = 0b000101101000;
      rows[6] = 0b001010010100;
      break;
    }
    case SCENE_FACE_HAPPY: {
      // Calm happy companion: steady smile for 4s, gentle blink at 3s, heart at 5s
      if (phase == 5) {
        // Gentle heart at end of 6s scene
        rows[0] = 0b000110011000;
        rows[1] = 0b001111111100;
        rows[2] = 0b011111111110;
        rows[3] = 0b011111111110;
        rows[4] = 0b001111111100;
        rows[5] = 0b000111111000;
        rows[6] = 0b000011110000;
        rows[7] = 0b000001100000;
      } else {
        const bool blink = (phase == 3);
        rows[1] = blink ? 0b000000000000 : 0b001100001100;
        rows[2] = 0b001100001100;
        rows[5] = 0b001000000100;
        rows[6] = 0b000111111000;
      }
      break;
    }
    case SCENE_THERMOMETER: {
      // Left cols 0..3: thermometer icon with slow mercury breathe (3s steady per step)
      const bool mercury_high = (phase < 3);
      rows[0] = 0b010000000001;  // top of stem + degree dot at col 11
      rows[1] = mercury_high ? 0b011000000000 : 0b010000000000;
      rows[2] = 0b010000000000;
      rows[3] = mercury_high ? 0b011000000000 : 0b010000000000;
      rows[4] = 0b010000000000;
      rows[5] = 0b111000000000;
      rows[6] = 0b111000000000;
      rows[7] = 0b010000000000;
      draw_two_digits(rows, static_cast<int>(lroundf(in.temperature_c)));
      break;
    }
    case SCENE_DROPLET: {
      // Left cols 0..3: water droplet with slow 3s shimmer; right cols 5..11: RH% integer
      const bool shimmer = (phase >= 3);
      rows[0] = 0b001000000000;
      rows[1] = 0b001000000000;
      rows[2] = 0b011100000000;
      rows[3] = shimmer ? 0b101100000000 : 0b111100000000;
      rows[4] = 0b111100000000;
      rows[5] = 0b111100000000;
      rows[6] = 0b011000000000;
      draw_two_digits(rows, static_cast<int>(lroundf(in.humidity_pct)));
      break;
    }
    case SCENE_LIGHTBULB: {
      // Left cols 0..3: glowing bulb icon with slow 3s breathe; right cols 5..11: 0..99 light %
      const bool rays = (phase < 3);
      rows[0] = rays ? 0b101000000000 : 0b010000000000;
      rows[1] = 0b011000000000;
      rows[2] = 0b111100000000;
      rows[3] = 0b111100000000;
      rows[4] = 0b011000000000;
      rows[5] = 0b011000000000;
      rows[6] = 0b011000000000;
      int light_pct = static_cast<int>(lroundf(in.light_ratio * 100.0f));
      if (light_pct > 99) {
        light_pct = 99;
      }
      draw_two_digits(rows, light_pct);
      break;
    }
    case SCENE_VOICE_WAVE: {
      // Animated Xiaoxi voice-chat waveform bars (300ms lively cadence during speech mode)
      const uint8_t vstep = static_cast<uint8_t>((now_ms / 300UL) % 3UL);
      rows[0] = (vstep == 1) ? 0b000010100000 : 0b000000000000;
      rows[1] = (vstep == 0) ? 0b000010100000 : 0b001010101000;
      rows[2] = (vstep == 2) ? 0b011011110110 : 0b001011110100;
      rows[3] = 0b111111111111;
      rows[4] = 0b111111111111;
      rows[5] = (vstep == 2) ? 0b011011110110 : 0b001011110100;
      rows[6] = (vstep == 0) ? 0b000010100000 : 0b001010101000;
      rows[7] = (vstep == 1) ? 0b000010100000 : 0b000000000000;
      break;
    }
  }

  if (in.publish_flash) {
    // Subtle top-right transmit indicator beacon at row 0 col 11
    rows[0] |= 0b000000000001;
  }

  pack_rows_12x8(rows, out_words);
  return scene;
}

}  // namespace led
}  // namespace xiaoxi

#endif
