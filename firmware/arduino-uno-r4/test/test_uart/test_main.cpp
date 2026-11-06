// Synthetic offline parser fixtures only; never published as node01 telemetry.
#include <unity.h>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include <string>
#include "sht31_uart.h"
#include "boot_state.h"
#include "led_companion.h"

void setUp() {}
void tearDown() {}

static unsigned feed_text(Sht31Parser& parser, const char* text, uint32_t now) {
    unsigned accepted = 0;
    for (std::size_t index = 0; index < std::strlen(text); ++index) {
        if (parser.feed(text[index], now)) ++accepted;
    }
    return accepted;
}

static void test_fragmented_crlf_and_exact_expiry() {
    Sht31Parser parser;
    TEST_ASSERT_FALSE(parser.fresh(0));
    TEST_ASSERT_EQUAL_UINT(0, feed_text(parser, "R:059.2RH 025.", 100));
    TEST_ASSERT_EQUAL_UINT(0, feed_text(parser, "7C\r", 200));
    TEST_ASSERT_FALSE(parser.fresh(200));
    TEST_ASSERT_TRUE(parser.feed('\n', 300));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 59.2f, parser.humidity());
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 25.7f, parser.temperature());
    TEST_ASSERT_TRUE(parser.fresh(5300));
    TEST_ASSERT_FALSE(parser.fresh(5301));
}

static void test_multiple_frames_negative_temperature_and_humidity_limits() {
    Sht31Parser parser;
    TEST_ASSERT_EQUAL_UINT(3, feed_text(parser,
        "R:000.0RH -005.5C\r\nR:100.0RH 000.0C\r\nR:059.2RH 025.7C\r\n", 42));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 25.7f, parser.temperature());
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 59.2f, parser.humidity());
    Sht31Parser negative;
    TEST_ASSERT_EQUAL_UINT(1, feed_text(negative, "R:000.0RH -005.5C\r\n", 0));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, -5.5f, negative.temperature());
    TEST_ASSERT_TRUE(negative.fresh(0));
}

static void test_invalid_frames_never_become_fresh() {
    const char* invalid[] = {
        "OK\r\n", "R:059.2RH 025.7C\n", "R:059.2RH 025.7C\rX\n",
        "R:059.2RH 025.7Cx\r\n", "R:059.2RH  025.7C\r\n",
        "R:NaNRH 025.7C\r\n", "R:059.2RH InfC\r\n",
        "R:101.0RH 025.7C\r\n", "R:-001.0RH 025.7C\r\n",
        "R:59e0RH 025.7C\r\n", "R:059.2RH +025.7C\r\n",
        "R:059.2RH 0x1.0C\r\n", "R:059.2RH 025.7C \r\n",
        " R:059.2RH 025.7C\r\n", "R:59RH 25C\r\n",
        "R:059.2RH 9999999999999999999999999999999999999999.0C\r\n"
    };
    for (const char* frame : invalid) {
        Sht31Parser parser;
        TEST_ASSERT_EQUAL_UINT_MESSAGE(0, feed_text(parser, frame, 1), frame);
        TEST_ASSERT_FALSE_MESSAGE(parser.fresh(1), frame);
    }
}

static void test_control_byte_discards_whole_line() {
    for (const char bad : {'\0', '\t', static_cast<char>(0xff)}) {
        Sht31Parser parser;
        feed_text(parser, "noise", 1);
        TEST_ASSERT_FALSE(parser.feed(bad, 1));
        TEST_ASSERT_EQUAL_UINT(0, feed_text(parser, "R:059.2RH 025.7C\r\n", 1));
        TEST_ASSERT_FALSE(parser.fresh(1));
        TEST_ASSERT_EQUAL_UINT(1, feed_text(parser, "R:059.2RH 025.7C\r\n", 2));
    }
}

static void test_overflow_suffix_is_not_a_new_frame() {
    Sht31Parser parser;
    for (unsigned index = 0; index < 80; ++index) parser.feed('X', 1);
    TEST_ASSERT_EQUAL_UINT(0, feed_text(parser, "R:059.2RH 025.7C\r\n", 1));
    TEST_ASSERT_FALSE(parser.fresh(1));
    TEST_ASSERT_EQUAL_UINT(1, feed_text(parser, "R:059.2RH 025.7C\r\n", 2));
}

static void test_invalid_frame_does_not_refresh_old_reading() {
    Sht31Parser parser;
    feed_text(parser, "R:059.2RH 025.7C\r\n", 100);
    TEST_ASSERT_EQUAL_UINT(0, feed_text(parser, "R:101.0RH 010.0C\r\n", 5100));
    TEST_ASSERT_TRUE(parser.fresh(5100));
    TEST_ASSERT_FALSE(parser.fresh(5101));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 25.7f, parser.temperature());
}

static void test_uint32_clock_wrap() {
    Sht31Parser parser;
    const uint32_t before_wrap = UINT32_MAX - 100;
    feed_text(parser, "R:059.2RH 025.7C\r\n", before_wrap);
    TEST_ASSERT_TRUE(parser.fresh(before_wrap + uint32_t(5000)));
    TEST_ASSERT_FALSE(parser.fresh(before_wrap + uint32_t(5001)));
}

static void test_expiration_cannot_resurrect_after_full_clock_cycle() {
    Sht31Parser parser;
    feed_text(parser, "R:059.2RH 025.7C\r\n", 100);
    TEST_ASSERT_FALSE(parser.fresh(5101));
    // Same uint32 value after a whole clock period must not revive old data.
    TEST_ASSERT_FALSE(parser.fresh(100));
    TEST_ASSERT_EQUAL_UINT(1, feed_text(parser, "R:060.0RH 026.0C\r\n", 101));
    TEST_ASSERT_TRUE(parser.fresh(101));
}

static void test_exact_buffer_boundary() {
    Sht31Parser parser;
    const std::string boundary = "R:" + std::string(46, '0') + "059.2RH 025.7C\r\n";
    TEST_ASSERT_EQUAL_UINT(1, feed_text(parser, boundary.c_str(), 1));
    const std::string too_long = "R:" + std::string(47, '0') + "059.2RH 025.7C\r\n";
    parser.reset();
    TEST_ASSERT_EQUAL_UINT(0, feed_text(parser, too_long.c_str(), 2));
    TEST_ASSERT_FALSE(parser.fresh(2));
}

static void test_arbitrary_bytes_remain_bounded_and_recover() {
    Sht31Parser parser;
    uint32_t random = 0x12345678U;
    for (uint32_t index = 0; index < 100000; ++index) {
        random = random * 1664525U + 1013904223U;
        parser.feed(static_cast<char>(random >> 24), index);
        parser.fresh(index);
    }
    parser.reset();
    TEST_ASSERT_FALSE(parser.fresh(100000));
    TEST_ASSERT_EQUAL_UINT(1, feed_text(parser, "R:059.2RH 025.7C\r\n", 100001));
}

static void test_reset_clears_reading_and_partial_frame() {
    Sht31Parser parser;
    feed_text(parser, "R:059.2RH 025.7C\r\nR:059.2RH ", 1);
    parser.reset();
    TEST_ASSERT_FALSE(parser.fresh(1));
    TEST_ASSERT_EQUAL_UINT(0, feed_text(parser, "025.7C\r\n", 2));
    TEST_ASSERT_EQUAL_UINT(1, feed_text(parser, "R:059.2RH 025.7C\r\n", 3));
}

static void test_queued_frame_uses_prior_empty_fifo_lower_bound() {
    Sht31Parser parser;
    // Caller observes an empty FIFO at100; frame is processed later at2500.
    feed_text(parser, "R:059.2RH 025.7C\r\n", 100);
    TEST_ASSERT_TRUE(parser.fresh(2500));
    TEST_ASSERT_TRUE(parser.fresh(5100));
    TEST_ASSERT_FALSE(parser.fresh(5101));
}

static void test_fragment_lower_bound_cannot_move_to_completion_time() {
    Sht31Parser parser;
    feed_text(parser, "R:059.2RH 025.", 100);
    // The caller preserves first-byte time, not the later LF processing time.
    feed_text(parser, "7C\r\n", 100);
    TEST_ASSERT_FALSE(parser.fresh(8000));
}

static void test_boot_counter_rejects_corruption_and_exhaustion() {
    BootRecord next = {};
    TEST_ASSERT_TRUE(next_boot({UINT32_MAX, UINT32_MAX, UINT32_MAX}, next));
    TEST_ASSERT_EQUAL_UINT32(1, next.counter);
    BootRecord previous = next;
    TEST_ASSERT_TRUE(next_boot(previous, next));
    TEST_ASSERT_EQUAL_UINT32(2, next.counter);
    TEST_ASSERT_FALSE(next_boot({0, 0, 0}, next));
    TEST_ASSERT_FALSE(next_boot({BOOT_MAGIC, 2, 2}, next));
    TEST_ASSERT_FALSE(next_boot({BOOT_MAGIC, UINT32_MAX, 0}, next));
}

static void test_backoff_is_bounded() {
    uint32_t delay_ms = 1000;
    for (uint32_t expected : {2000U, 4000U, 8000U, 16000U, 32000U, 60000U, 60000U}) {
        delay_ms = next_backoff(delay_ms);
        TEST_ASSERT_EQUAL_UINT32(expected, delay_ms);
    }
}

static void test_ldr_adc_normalization_bounds() {
    float light = -1.0f;
    TEST_ASSERT_TRUE(normalize_ldr_adc(0, light));
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 1.0f, light);
    TEST_ASSERT_TRUE(normalize_ldr_adc(1023, light));
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 0.0f, light);
    TEST_ASSERT_TRUE(normalize_ldr_adc(512, light));
    TEST_ASSERT_FLOAT_WITHIN(0.001f, 511.0f / 1023.0f, light);
    TEST_ASSERT_FALSE(normalize_ldr_adc(-1, light));
    TEST_ASSERT_FALSE(normalize_ldr_adc(1024, light));
}

static void test_led_companion_scenes_and_pixel_packing() {
    using namespace xiaoxi::led;
    uint32_t words_a[3] = {0, 0, 0};
    uint32_t words_b[3] = {0, 0, 0};

    // Fault state preempts everything with crying animation
    CompanionInput fault = {true, false, true, 24.0f, 55.0f, 0.30f, false};
    TEST_ASSERT_EQUAL_UINT8(SCENE_ALERT_CRY, render_companion_frame(fault, 0, words_a));
    TEST_ASSERT_EQUAL_UINT8(SCENE_ALERT_CRY, render_companion_frame(fault, kPhaseDurationMs, words_b));
    TEST_ASSERT_TRUE(words_a[0] != words_b[0] || words_a[2] != words_b[2]);

    // Offline network shows connecting animation
    CompanionInput offline = {false, true, true, 24.0f, 55.0f, 0.30f, false};
    TEST_ASSERT_EQUAL_UINT8(SCENE_CONNECTING, render_companion_frame(offline, 0, words_a));

    // Dark room (<10%) keeps full 4-scene carousel and adds sleepy Zzz face as 5th slot
    CompanionInput dark = {true, true, true, 24.0f, 55.0f, 0.05f, false};
    TEST_ASSERT_EQUAL_UINT8(SCENE_FACE_HAPPY, render_companion_frame(dark, 0, words_a));
    TEST_ASSERT_EQUAL_UINT8(SCENE_THERMOMETER, render_companion_frame(dark, kSceneDurationMs, words_b));
    TEST_ASSERT_EQUAL_UINT8(SCENE_DROPLET, render_companion_frame(dark, kSceneDurationMs * 2, words_b));
    TEST_ASSERT_EQUAL_UINT8(SCENE_LIGHTBULB, render_companion_frame(dark, kSceneDurationMs * 3, words_b));
    TEST_ASSERT_EQUAL_UINT8(SCENE_FACE_SLEEPY, render_companion_frame(dark, kSceneDurationMs * 4, words_b));

    // Normal carousel cycles happy -> thermometer -> droplet -> lightbulb every 6.0s
    CompanionInput normal = {true, true, true, 24.0f, 55.0f, 0.27f, true};
    TEST_ASSERT_EQUAL_UINT8(SCENE_FACE_HAPPY, render_companion_frame(normal, 0, words_a));
    TEST_ASSERT_TRUE(get_pixel_12x8(words_a, 0, 11));  // publish_flash beacon at top-right
    TEST_ASSERT_EQUAL_UINT8(SCENE_THERMOMETER, render_companion_frame(normal, kSceneDurationMs, words_a));
    TEST_ASSERT_EQUAL_UINT8(SCENE_DROPLET, render_companion_frame(normal, kSceneDurationMs * 2, words_a));
    TEST_ASSERT_EQUAL_UINT8(SCENE_LIGHTBULB, render_companion_frame(normal, kSceneDurationMs * 3, words_a));

    // Hot/humid state switches face slot to sweating face
    CompanionInput hot = {true, true, true, 30.5f, 55.0f, 0.27f, false};
    TEST_ASSERT_EQUAL_UINT8(SCENE_FACE_HOT, render_companion_frame(hot, 0, words_a));

    // Voice mode overrides normal carousel with animated voice waveform
    CompanionInput voice = {true, true, true, 24.0f, 55.0f, 0.27f, false, true, 0};
    TEST_ASSERT_EQUAL_UINT8(SCENE_VOICE_WAVE, render_companion_frame(voice, 0, words_a));

    // 3-wire unmarked button gesture state machine: single, double, and long press
    ButtonGestureTracker tracker;
    tracker.init(0x3Fu);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 100));
    // Single press (held 100ms, released, wait 400ms)
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 110));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 150));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 210));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 250));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_SINGLE_PRESS, tracker.update(0x3Fu, 650));

    // Long press (held >= 700ms after debounce)
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 1000));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 1040));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_PRESS, tracker.update(0x3Bu, 1750));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1800));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1829));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_RELEASE, tracker.update(0x3Fu, 1830));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1830));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 2300));
}

static void test_button_long_hold_does_not_rebaseline() {
    using namespace xiaoxi::led;
    ButtonGestureTracker tracker;
    tracker.init(0x3Fu);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 100));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 130));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_PRESS, tracker.update(0x3Bu, 830));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 4100));
    TEST_ASSERT_EQUAL_HEX8(0x3Fu, tracker.baseline_mask);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 12000));
    TEST_ASSERT_EQUAL_HEX8(0x3Fu, tracker.baseline_mask);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 12100));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_RELEASE, tracker.update(0x3Fu, 12130));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 12510));
}

static void test_button_long_release_bounce_and_next_press() {
    using namespace xiaoxi::led;
    ButtonGestureTracker tracker;
    tracker.init(0x3Fu);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 100));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 130));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_PRESS, tracker.update(0x3Bu, 830));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 900));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 910));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 940));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 950));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 979));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_RELEASE, tracker.update(0x3Fu, 980));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 980));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 990));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1000));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1030));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 1050));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 1080));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1150));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1180));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1559));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_SINGLE_PRESS, tracker.update(0x3Fu, 1560));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 2000));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 2100));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 2130));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_PRESS, tracker.update(0x3Bu, 2830));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 2900));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_RELEASE, tracker.update(0x3Fu, 2930));
}

static void test_button_single_and_double_press() {
    using namespace xiaoxi::led;
    ButtonGestureTracker tracker;
    tracker.init(0x3Fu);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 100));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 130));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 200));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 230));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 609));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_SINGLE_PRESS, tracker.update(0x3Fu, 610));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 700));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 730));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 800));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 830));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 900));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 930));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1000));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_DOUBLE_PRESS, tracker.update(0x3Fu, 1030));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1030));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, 1500));
}

static void test_button_initialization_and_idle_rebaseline() {
    using namespace xiaoxi::led;
    ButtonGestureTracker tracker;
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 0));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, 5000));
    TEST_ASSERT_EQUAL_HEX8(0x3Bu, tracker.baseline_mask);
    tracker.init(0x3Fu);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 100));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 4099));
    TEST_ASSERT_EQUAL_HEX8(0x3Fu, tracker.baseline_mask);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 4100));
    TEST_ASSERT_EQUAL_HEX8(0x3Eu, tracker.baseline_mask);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 9000));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Cu, 10000));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Cu, 10030));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_PRESS, tracker.update(0x3Cu, 10730));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Eu, 10800));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_RELEASE, tracker.update(0x3Eu, 10830));
}

static void test_button_long_release_across_clock_wrap() {
    using namespace xiaoxi::led;
    ButtonGestureTracker tracker;
    const uint32_t start = UINT32_MAX - 300U;
    tracker.init(0x3Fu, start);
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, start + 100U));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, start + 130U));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Bu, start + 829U));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_PRESS, tracker.update(0x3Bu, start + 830U));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, start + 900U));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, start + 929U));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_LONG_RELEASE, tracker.update(0x3Fu, start + 930U));
    TEST_ASSERT_EQUAL_UINT8(BUTTON_GESTURE_NONE, tracker.update(0x3Fu, start + 1400U));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_queued_frame_uses_prior_empty_fifo_lower_bound);
    RUN_TEST(test_fragment_lower_bound_cannot_move_to_completion_time);
    RUN_TEST(test_boot_counter_rejects_corruption_and_exhaustion);
    RUN_TEST(test_backoff_is_bounded);
    RUN_TEST(test_ldr_adc_normalization_bounds);
    RUN_TEST(test_led_companion_scenes_and_pixel_packing);
    RUN_TEST(test_button_long_hold_does_not_rebaseline);
    RUN_TEST(test_button_long_release_bounce_and_next_press);
    RUN_TEST(test_button_single_and_double_press);
    RUN_TEST(test_button_initialization_and_idle_rebaseline);
    RUN_TEST(test_button_long_release_across_clock_wrap);
    RUN_TEST(test_fragmented_crlf_and_exact_expiry);
    RUN_TEST(test_multiple_frames_negative_temperature_and_humidity_limits);
    RUN_TEST(test_invalid_frames_never_become_fresh);
    RUN_TEST(test_control_byte_discards_whole_line);
    RUN_TEST(test_overflow_suffix_is_not_a_new_frame);
    RUN_TEST(test_invalid_frame_does_not_refresh_old_reading);
    RUN_TEST(test_uint32_clock_wrap);
    RUN_TEST(test_expiration_cannot_resurrect_after_full_clock_cycle);
    RUN_TEST(test_reset_clears_reading_and_partial_frame);
    RUN_TEST(test_exact_buffer_boundary);
    RUN_TEST(test_arbitrary_bytes_remain_bounded_and_recover);
    return UNITY_END();
}
