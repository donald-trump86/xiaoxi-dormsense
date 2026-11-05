#include <unity.h>
#include <cstring>
#include "ir_node_logic.h"
#include "ir_raw_timing.h"

using namespace xiaoxi::ir;

void setUp() {}
void tearDown() {}

void test_supported_protocols_and_ac_spec_bounds() {
  AcSpec spec{};
  TEST_ASSERT_TRUE(validate_ac_spec("GREE", true, "cool", 26, "auto", spec));
  TEST_ASSERT_EQUAL_STRING("GREE", spec.protocol);
  TEST_ASSERT_TRUE(spec.power);
  TEST_ASSERT_EQUAL_UINT8(AC_MODE_COOL, spec.mode);
  TEST_ASSERT_EQUAL_UINT8(26, spec.temp_c);
  TEST_ASSERT_EQUAL_UINT8(AC_FAN_AUTO, spec.fan);

  TEST_ASSERT_TRUE(validate_ac_spec("MIDEA", false, "dry", 24, "low", spec));
  TEST_ASSERT_TRUE(validate_ac_spec("HAIER_AC_YRW02", true, "heat", 20, "high", spec));

  // Reject out-of-range temperatures or unknown brands/modes
  TEST_ASSERT_FALSE(validate_ac_spec("GREE", true, "cool", 15, "auto", spec));
  TEST_ASSERT_FALSE(validate_ac_spec("GREE", true, "cool", 31, "auto", spec));
  TEST_ASSERT_FALSE(validate_ac_spec("UNKNOWN_TV", true, "cool", 26, "auto", spec));
  TEST_ASSERT_FALSE(validate_ac_spec("GREE", true, "turbo_blast", 26, "auto", spec));
}

void test_command_deduplicator_and_ttl() {
  CommandDeduplicator dedup;
  TEST_ASSERT_FALSE(dedup.seen_or_record("cmd-001"));
  TEST_ASSERT_TRUE(dedup.seen_or_record("cmd-001"));
  TEST_ASSERT_FALSE(dedup.seen_or_record("cmd-002"));
  TEST_ASSERT_TRUE(dedup.seen_or_record(""));

  TEST_ASSERT_TRUE(is_valid_ttl(1));
  TEST_ASSERT_TRUE(is_valid_ttl(30));
  TEST_ASSERT_FALSE(is_valid_ttl(0));
  TEST_ASSERT_FALSE(is_valid_ttl(31));
}

void test_loopback_frame_matcher() {
  TEST_ASSERT_TRUE(matches_loopback_frame("NEC", LOOPBACK_NEC_CODE, LOOPBACK_NEC_BITS));
  TEST_ASSERT_FALSE(matches_loopback_frame("NEC", 0x12345678ULL, 32));
  TEST_ASSERT_FALSE(matches_loopback_frame("GREE", LOOPBACK_NEC_CODE, 32));
}

void test_raw_timing_fixed_units_and_format() {
  const uint16_t ticks[] = {1, 4480, 2240, 280, 840};
  char out[320] = {};
  TEST_ASSERT_TRUE(format_raw_timing_part(ticks, 5, false, 17, 0, out, sizeof(out)));
  TEST_ASSERT_EQUAL_STRING(
      "raw_timing capture=17 rawlen=5 kept=5 truncated=0 overflow=0 offset=0 count=5 unit=us times=2,8960,4480,560,1680",
      out);
}

void test_raw_timing_chunks_are_bounded() {
  uint16_t ticks[300];
  for (auto& value : ticks) value = 65535;
  char out[320] = {};
  TEST_ASSERT_TRUE(format_raw_timing_part(ticks, 301, true, 4294967295U, 272, out, sizeof(out)));
  TEST_ASSERT_NOT_NULL(std::strstr(out, "kept=300 truncated=1 overflow=1 offset=272 count=16"));
  TEST_ASSERT_NOT_NULL(std::strstr(out, "times=131070,131070"));
  TEST_ASSERT_TRUE(std::strlen(out) < 300);
  TEST_ASSERT_TRUE(format_raw_timing_part(ticks, 68, false, 0, 64, out, sizeof(out)));
  TEST_ASSERT_NOT_NULL(std::strstr(out, "offset=64 count=4 unit=us times=131070,131070,131070,131070"));
}

void test_raw_timing_rejects_invalid_or_short_buffers() {
  const uint16_t ticks[] = {1, 10};
  char out[320] = {};
  TEST_ASSERT_FALSE(format_raw_timing_part(nullptr, 2, false, 0, 0, out, sizeof(out)));
  TEST_ASSERT_FALSE(format_raw_timing_part(ticks, 0, false, 0, 0, out, sizeof(out)));
  TEST_ASSERT_FALSE(format_raw_timing_part(ticks, 2, false, 0, 1, out, sizeof(out)));
  TEST_ASSERT_FALSE(format_raw_timing_part(ticks, 2, false, 0, 16, out, sizeof(out)));
  TEST_ASSERT_FALSE(format_raw_timing_part(ticks, 2, false, 0, 0, nullptr, sizeof(out)));
  char tiny[] = {'X', 'X', 'X', 'Q'};
  TEST_ASSERT_FALSE(format_raw_timing_part(ticks, 2, false, 0, 0, tiny, 3));
  TEST_ASSERT_EQUAL_CHAR('Q', tiny[3]);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_supported_protocols_and_ac_spec_bounds);
  RUN_TEST(test_command_deduplicator_and_ttl);
  RUN_TEST(test_loopback_frame_matcher);
  RUN_TEST(test_raw_timing_fixed_units_and_format);
  RUN_TEST(test_raw_timing_chunks_are_bounded);
  RUN_TEST(test_raw_timing_rejects_invalid_or_short_buffers);
  return UNITY_END();
}
