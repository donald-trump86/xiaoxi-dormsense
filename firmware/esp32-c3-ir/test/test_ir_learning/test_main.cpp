#include <unity.h>
#include <string>
#include "ir_learning.h"

using namespace xiaoxi::ir;
static CommandParser parser;
static WireCommand command;
constexpr char kBoot[] = "node02-00000001";

void setUp() {}
void tearDown() {}

std::string request(const char* action, const std::string& fields = "",
                    const char* id = "cmd_1") {
  return std::string("{\"schema_version\":\"1.0\",\"node_id\":\"node02\",\"command_id\":\"") +
      id + "\",\"ttl_seconds\":30,\"action\":\"" + action + "\"" + fields + "}";
}
std::string identity(uint32_t deadline = 1000) {
  return std::string(",\"boot_id\":\"") + kBoot + "\",\"deadline_ms\":" +
      std::to_string(deadline);
}
bool parse(const std::string& data, uint32_t now = 100) {
  return parser.parse(data.data(), data.size(), kBoot, now, command);
}
std::string timings(size_t count, unsigned int duration = 560) {
  std::string result = ",\"frequency_khz\":38,\"timings_us\":[";
  for (size_t i = 0; i < count; ++i) {
    if (i) result += ',';
    result += std::to_string(duration);
  }
  return result + ']';
}

void test_status_and_session_types_bounds() {
  TEST_ASSERT_TRUE(parse(request("ir_status")));
  TEST_ASSERT_EQUAL_INT(static_cast<int>(WireAction::Status),
                        static_cast<int>(command.action));
  const auto valid = identity() + ",\"session_id\":\"session_1\",\"window_seconds\":60";
  TEST_ASSERT_TRUE(parse(request("ir_learn_start", valid)));
  TEST_ASSERT_EQUAL_STRING("session_1", command.session_id);
  TEST_ASSERT_EQUAL_UINT8(60, command.window_seconds);
  for (const char* bad : {"0", "61", "true", "\"1\"", "1.0", "1e0", "-1"}) {
    TEST_ASSERT_FALSE(parse(request("ir_learn_start", identity() +
        ",\"session_id\":\"s\",\"window_seconds\":" + bad)));
  }
  TEST_ASSERT_FALSE(parse(request("ir_status", ",\"boot_id\":\"old\"")));
  TEST_ASSERT_FALSE(parse(request("ir_status", "", "bad.id")));
  const std::string max_id(40, 'a');
  TEST_ASSERT_TRUE(parse(request("ir_status", "", max_id.c_str())));
  CommandDeduplicator dedup;
  TEST_ASSERT_FALSE(dedup.seen_or_record(max_id.c_str()));
  TEST_ASSERT_TRUE(dedup.seen_or_record(max_id.c_str()));
  TEST_ASSERT_FALSE(parse(request("ir_status", "", std::string(41, 'a').c_str())));
}

void test_strict_json_duplicates_unknown_and_capacity() {
  TEST_ASSERT_FALSE(parse(request("ir_status", ",\"action\":\"ir_status\"")));
  TEST_ASSERT_FALSE(parse(request("ir_status", ",\"ttl_seconds\":30")));
  TEST_ASSERT_FALSE(parse(request("ir_status", ",\"extra\":true")));
  TEST_ASSERT_FALSE(parse(request("ir_status", ",\"nested\":{\"x\":1}")));
  TEST_ASSERT_FALSE(parse(request("ir_status") + "garbage"));
  TEST_ASSERT_FALSE(parse(request("ir_status") + std::string(2560, ' ')));
  TEST_ASSERT_FALSE(parse("{'schema_version':'1.0'}"));
  TEST_ASSERT_FALSE(parse("{schema_version:\"1.0\"}"));
  TEST_ASSERT_FALSE(parse(request("ir_status", ",\"a\\u0063tion\":\"ir_status\"")));
  auto zero = request("ir_status");
  zero.insert(zero.find("30"), "0");
  TEST_ASSERT_FALSE(parse(zero));
  auto embedded_null = request("ir_status");
  embedded_null.insert(10, 1, '\0');
  TEST_ASSERT_FALSE(parse(embedded_null));
}

void test_boot_deadline_and_uint32_wrap() {
  const auto session = ",\"session_id\":\"s\"";
  TEST_ASSERT_TRUE(parse(request("ir_learn_cancel", identity(101) + session)));
  TEST_ASSERT_TRUE(parse(request("ir_learn_cancel", identity(10100) + session)));
  TEST_ASSERT_FALSE(parse(request("ir_learn_cancel", identity(100) + session)));
  TEST_ASSERT_FALSE(parse(request("ir_learn_cancel", identity(99) + session)));
  TEST_ASSERT_FALSE(parse(request("ir_learn_cancel", identity(10101) + session)));
  TEST_ASSERT_TRUE(parse(request("ir_learn_cancel", identity(10) + session), UINT32_MAX - 5));
  auto old_boot = request("ir_learn_cancel", identity() + session);
  old_boot.replace(old_boot.find(kBoot), std::strlen(kBoot), "node02-00000000");
  TEST_ASSERT_FALSE(parse(old_boot));
  TEST_ASSERT_FALSE(parse(request("ir_learn_cancel", ",\"session_id\":\"s\"")));
  TEST_ASSERT_FALSE(parse(request("ir_learn_cancel", identity() + session +
                                 ",\"deadline_ms\":4294967296")));
}

void test_replay_waveform_integer_count_duration_and_carrier_bounds() {
  TEST_ASSERT_TRUE(parse(request("ir_raw_prepare", identity() + timings(15, 1))));
  TEST_ASSERT_EQUAL_UINT16(15, command.timing_count);
  TEST_ASSERT_TRUE(parse(request("ir_raw_prepare", identity() + timings(299))));
  TEST_ASSERT_EQUAL_UINT16(299, command.timing_count);
  for (size_t count : {0U, 14U, 16U, 298U, 300U, 301U})
    TEST_ASSERT_FALSE(parse(request("ir_raw_prepare", identity() + timings(count))));
  for (unsigned int value : {0U, 65536U, 70000U})
    TEST_ASSERT_FALSE(parse(request("ir_raw_prepare", identity() + timings(15, value))));
  TEST_ASSERT_TRUE(parse(request("ir_raw_prepare", identity() + timings(15, 65535))));
  TEST_ASSERT_FALSE(parse(request("ir_raw_prepare", identity() + timings(17, 65535))));
  auto wrong_carrier = identity() + timings(15);
  wrong_carrier.replace(wrong_carrier.find(":38"), 3, ":40");
  TEST_ASSERT_FALSE(parse(request("ir_raw_prepare", wrong_carrier)));
  for (const char* invalid : {"true", "1.0", "\"560\"", "-1"}) {
    auto field = identity() + timings(15);
    field.replace(field.find("560"), 3, invalid);
    TEST_ASSERT_FALSE(parse(request("ir_raw_prepare", field)));
  }
}

void test_window_capture_cancel_and_expiry_are_once() {
  LearningWindow window;
  WireCommand start;
  std::strcpy(start.session_id, "session");
  start.window_seconds = 1;
  window.start(start, UINT32_MAX - 500);
  char session[41] = {};
  TEST_ASSERT_TRUE(window.consume(0, session));
  TEST_ASSERT_EQUAL_STRING("session", session);
  TEST_ASSERT_FALSE(window.consume(1, session));
  window.start(start, 100);
  TEST_ASSERT_FALSE(window.cancel("foreign"));
  TEST_ASSERT_TRUE(window.cancel("session"));
  TEST_ASSERT_FALSE(window.cancel("session"));
  window.start(start, 100);
  TEST_ASSERT_FALSE(window.expire(1099));
  TEST_ASSERT_TRUE(window.expire(1100));
  TEST_ASSERT_FALSE(window.expire(1101));
  TEST_ASSERT_FALSE(window.consume(1101, session));
}

void test_preparation_overwrite_challenge_consume_and_expiry() {
  TEST_ASSERT_TRUE(parse(request("ir_raw_prepare", identity() + timings(15))));
  RawPreparation prep;
  RawWaveform output;
  const char* a = "0123456789abcdef0123456789abcdef";
  const char* b = "abcdef0123456789abcdef0123456789";
  prep.prepare(command, a, UINT32_MAX - 100);
  TEST_ASSERT_FALSE(prep.take(b, 0, output));
  TEST_ASSERT_TRUE(prep.pending);
  TEST_ASSERT_TRUE(prep.take(a, 0, output));
  TEST_ASSERT_FALSE(prep.pending);
  TEST_ASSERT_EQUAL_UINT16(15, output.count);
  TEST_ASSERT_EQUAL_UINT16(560, output.timings[0]);
  TEST_ASSERT_FALSE(prep.take(a, 1, output));
  prep.prepare(command, a, 100);
  prep.prepare(command, b, 101);
  TEST_ASSERT_FALSE(prep.take(a, 102, output));
  TEST_ASSERT_TRUE(prep.take(b, 102, output));
  prep.prepare(command, a, 100);
  TEST_ASSERT_FALSE(prep.take(a, 10100, output));
  TEST_ASSERT_FALSE(prep.pending);
  TEST_ASSERT_FALSE(parse(request("ir_raw_commit", identity() +
      ",\"challenge\":\"0123456789ABCDEF0123456789ABCDEF\"")));
}

void test_json_event_escaping_and_envelope_bounds() {
  char output[1024];
  const char* detail = "{\"kind\":\"capture\",\"slash\":\"\\\\\"}\n";
  TEST_ASSERT_TRUE(format_event_envelope(kBoot, UINT32_MAX, "ir_learning", "info",
                                        detail, output, sizeof(output)));
  StaticJsonDocument<2048> event;
  TEST_ASSERT_FALSE(deserializeJson(event, output));
  TEST_ASSERT_EQUAL_STRING(detail, event["detail"].as<const char*>());
  TEST_ASSERT_EQUAL_STRING("1.0", event["schema_version"].as<const char*>());
  TEST_ASSERT_TRUE(event["timestamp"].isNull());
  TEST_ASSERT_FALSE(event["simulated"].as<bool>());
  TEST_ASSERT_FALSE(format_event_envelope(kBoot, 1, "ir_learning", "info",
      std::string(513, 'x').c_str(), output, sizeof(output)));
  TEST_ASSERT_FALSE(format_event_envelope(kBoot, 1, "ir_learning", "info",
      std::string(512, '"').c_str(), output, sizeof(output)));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_status_and_session_types_bounds);
  RUN_TEST(test_strict_json_duplicates_unknown_and_capacity);
  RUN_TEST(test_boot_deadline_and_uint32_wrap);
  RUN_TEST(test_replay_waveform_integer_count_duration_and_carrier_bounds);
  RUN_TEST(test_window_capture_cancel_and_expiry_are_once);
  RUN_TEST(test_preparation_overwrite_challenge_consume_and_expiry);
  RUN_TEST(test_json_event_escaping_and_envelope_bounds);
  return UNITY_END();
}
