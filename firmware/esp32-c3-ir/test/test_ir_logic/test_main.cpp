#include <unity.h>
#include "ir_node_logic.h"

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

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_supported_protocols_and_ac_spec_bounds);
  RUN_TEST(test_command_deduplicator_and_ttl);
  RUN_TEST(test_loopback_frame_matcher);
  return UNITY_END();
}
