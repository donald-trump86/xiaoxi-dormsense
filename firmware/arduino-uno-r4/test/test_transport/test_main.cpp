// Host-only synthetic transport tests; no Arduino, network, or hardware access.
#include <unity.h>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <string>

static uint32_t now_ms = 0;
uint32_t millis() { return now_ms; }

class IPAddress {
public:
    IPAddress(uint8_t a = 127, uint8_t b = 0, uint8_t c = 0, uint8_t d = 1)
        : address_(std::to_string(a) + "." + std::to_string(b) + "." +
                   std::to_string(c) + "." + std::to_string(d)) {}
    std::string toString() const { return address_; }
private:
    std::string address_;
};

// Each base operation can advance the clock before returning. Public counters
// distinguish real bytes/calls from bytes merely promised by the wrapper.
class WiFiSSLClient {
public:
    virtual ~WiFiSSLClient() = default;
    std::deque<uint8_t> incoming;
    std::deque<uint8_t> outgoing;
    bool open = false;
    bool fail_read = false;
    int connect_result = 1;
    int advertised_available = -1; // -1: use the real queue size.
    uint8_t connected_result = 1;
    std::size_t write_limit = static_cast<std::size_t>(-1);
    uint32_t connect_delay = 0;
    uint32_t write_delay = 0;
    uint32_t available_delay = 0;
    uint32_t read_delay = 0;
    uint32_t peek_delay = 0;
    uint32_t flush_delay = 0;
    uint32_t connected_delay = 0;
    uint32_t stop_delay = 0;
    unsigned host_connect_calls = 0;
    unsigned ip_connect_calls = 0;
    unsigned write_calls = 0;
    unsigned available_calls = 0;
    unsigned read_calls = 0;
    unsigned peek_calls = 0;
    unsigned flush_calls = 0;
    unsigned connected_calls = 0;
    unsigned stop_calls = 0;
    unsigned received_bytes = 0;

    virtual int connect(const char*, uint16_t) {
        ++host_connect_calls;
        return finish_connect();
    }
    virtual int connect(IPAddress, uint16_t) {
        ++ip_connect_calls;
        return finish_connect();
    }
    virtual std::size_t write(uint8_t byte) {
        return finish_write(&byte, 1);
    }
    virtual std::size_t write(const uint8_t* bytes, std::size_t size) {
        return finish_write(bytes, size);
    }
    virtual int available() {
        ++available_calls;
        now_ms += available_delay;
        if (!open) return 0;
        return advertised_available >= 0 ? advertised_available
                                        : static_cast<int>(incoming.size());
    }
    virtual int read() {
        ++read_calls;
        now_ms += read_delay;
        return take_byte();
    }
    virtual int read(uint8_t* bytes, std::size_t size) {
        ++read_calls;
        now_ms += read_delay;
        if (!open || fail_read) return -1;
        std::size_t count = 0;
        while (count < size && !incoming.empty()) {
            bytes[count++] = static_cast<uint8_t>(take_byte());
        }
        return static_cast<int>(count);
    }
    virtual int peek() {
        ++peek_calls;
        now_ms += peek_delay;
        return open && !incoming.empty() ? incoming.front() : -1;
    }
    virtual void flush() {
        ++flush_calls;
        now_ms += flush_delay;
    }
    virtual uint8_t connected() {
        ++connected_calls;
        now_ms += connected_delay;
        return open ? connected_result : 0;
    }
    virtual void stop() {
        ++stop_calls;
        now_ms += stop_delay;
        open = false;
    }

private:
    int finish_connect() {
        now_ms += connect_delay;
        open = connect_result != 0;
        return connect_result;
    }
    std::size_t finish_write(const uint8_t* bytes, std::size_t size) {
        ++write_calls;
        now_ms += write_delay;
        if (!open) return 0;
        const std::size_t count = size < write_limit ? size : write_limit;
        for (std::size_t index = 0; index < count; ++index) {
            outgoing.push_back(bytes[index]);
        }
        return count;
    }
    int take_byte() {
        if (!open || fail_read || incoming.empty()) return -1;
        const uint8_t byte = incoming.front();
        incoming.pop_front();
        ++received_bytes;
        return byte;
    }
};

#include "deadline_tls.h"

void setUp() { now_ms = 0; }
void tearDown() {}

static void start_session(DeadlineTLSClient& client) {
    client.arm();
    TEST_ASSERT_EQUAL_INT(1, client.connect("example.invalid", 443));
}

static void test_cached_byte_survives_available_read_deadline_race() {
    DeadlineTLSClient client;
    start_session(client);
    client.incoming.push_back(0x42);
    now_ms = 2999;
    TEST_ASSERT_EQUAL_INT(1, client.available());
    TEST_ASSERT_EQUAL_INT(1, client.available());
    TEST_ASSERT_EQUAL_UINT(1, client.received_bytes);
    now_ms = 3000;
    TEST_ASSERT_EQUAL_INT(0x42, client.read());
    TEST_ASSERT_EQUAL_INT(-1, client.read());
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    TEST_ASSERT_EQUAL_UINT(1, client.read_calls);
    client.arm();
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_INT(-1, client.read());
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
}

static void test_available_crossing_deadline_stops_before_prefetch() {
    DeadlineTLSClient client;
    start_session(client);
    client.incoming.push_back(0x21);
    now_ms = 2999;
    client.available_delay = 1;
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_UINT(1, client.available_calls);
    TEST_ASSERT_EQUAL_UINT(0, client.read_calls);
    TEST_ASSERT_EQUAL_UINT(0, client.received_bytes);
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    TEST_ASSERT_EQUAL_INT(-1, client.read());
}

static void test_prefetch_read_crossing_deadline_never_promises_a_byte() {
    DeadlineTLSClient client;
    start_session(client);
    client.incoming.push_back(0x32);
    now_ms = 2999;
    client.read_delay = 1;
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_UINT(1, client.received_bytes);
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    TEST_ASSERT_EQUAL_INT(-1, client.read());
    client.arm();
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_UINT(1, client.read_calls);
}

static void test_available_requires_a_real_byte_and_negative_read_latches_fault() {
    DeadlineTLSClient client;
    start_session(client);
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_UINT(0, client.read_calls);
    TEST_ASSERT_EQUAL_UINT(0, client.stop_calls);
    client.advertised_available = 1;
    client.fail_read = true;
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_UINT(0, client.received_bytes);
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    client.fail_read = false;
    client.incoming.push_back(0x55);
    client.arm();
    TEST_ASSERT_EQUAL_INT(-1, client.read());
    TEST_ASSERT_EQUAL_UINT(1, client.read_calls);
}

static void test_short_write_arm_does_not_revive_but_connect_recovers() {
    DeadlineTLSClient client;
    start_session(client);
    const uint8_t bytes[] = {1, 2, 3};
    client.write_limit = 2;
    TEST_ASSERT_TRUE(client.write(bytes, sizeof(bytes)) < sizeof(bytes));
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    TEST_ASSERT_EQUAL_UINT(1, client.write_calls);
    client.write_limit = sizeof(bytes);
    client.arm();
    TEST_ASSERT_EQUAL_UINT(0, client.write(bytes, sizeof(bytes)));
    TEST_ASSERT_EQUAL_UINT(0, client.write(uint8_t(9)));
    TEST_ASSERT_EQUAL_UINT(1, client.write_calls);
    TEST_ASSERT_EQUAL_INT(1, client.connect("example.invalid", 443));
    TEST_ASSERT_EQUAL_UINT(sizeof(bytes), client.write(bytes, sizeof(bytes)));
    TEST_ASSERT_EQUAL_UINT(1, client.write(uint8_t(9)));
    TEST_ASSERT_EQUAL_UINT(2, client.host_connect_calls);
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
}

static void test_single_byte_short_write_stops_session() {
    DeadlineTLSClient client;
    start_session(client);
    client.write_limit = 0;
    TEST_ASSERT_EQUAL_UINT(0, client.write(uint8_t(7)));
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    client.arm();
    client.write_limit = 1;
    TEST_ASSERT_EQUAL_UINT(0, client.write(uint8_t(7)));
    TEST_ASSERT_EQUAL_UINT(1, client.write_calls);
}

static void test_writes_recheck_deadline_after_base_call() {
    const uint8_t bytes[] = {4, 5};
    for (unsigned variant = 0; variant < 2; ++variant) {
        now_ms = 0;
        DeadlineTLSClient client;
        start_session(client);
        now_ms = 2999;
        client.write_delay = 1;
        const std::size_t written = variant == 0
            ? client.write(uint8_t(4)) : client.write(bytes, sizeof(bytes));
        TEST_ASSERT_EQUAL_UINT(0, written);
        TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
        client.arm();
        TEST_ASSERT_EQUAL_UINT(0, client.write(uint8_t(6)));
        TEST_ASSERT_EQUAL_UINT(1, client.write_calls);
    }
}

static void test_connected_crossing_deadline_latches_fault() {
    DeadlineTLSClient client;
    start_session(client);
    now_ms = 2999;
    client.connected_delay = 1;
    TEST_ASSERT_EQUAL_UINT8(0, client.connected());
    TEST_ASSERT_EQUAL_UINT(1, client.connected_calls);
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    client.arm();
    TEST_ASSERT_EQUAL_UINT8(0, client.connected());
    TEST_ASSERT_EQUAL_UINT(1, client.connected_calls);
}

static void test_flush_rechecks_deadline_after_base_call() {
    DeadlineTLSClient client;
    start_session(client);
    now_ms = 2999;
    client.flush_delay = 1;
    client.flush();
    TEST_ASSERT_EQUAL_UINT(1, client.flush_calls);
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    client.arm();
    client.flush();
    TEST_ASSERT_EQUAL_UINT(1, client.flush_calls);
}

static void test_stop_is_idempotent_and_arm_cannot_revive_stopped_session() {
    DeadlineTLSClient client;
    start_session(client);
    client.stop();
    client.stop();
    client.arm();
    TEST_ASSERT_EQUAL_UINT(0, client.write(uint8_t(1)));
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_INT(-1, client.read());
    TEST_ASSERT_EQUAL_INT(-1, client.peek());
    TEST_ASSERT_EQUAL_UINT8(0, client.connected());
    client.flush();
    client.stop();
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    TEST_ASSERT_EQUAL_UINT(0, client.write_calls);
    TEST_ASSERT_EQUAL_UINT(0, client.available_calls);
    TEST_ASSERT_EQUAL_UINT(0, client.read_calls);
    TEST_ASSERT_EQUAL_UINT(0, client.peek_calls);
    TEST_ASSERT_EQUAL_UINT(0, client.connected_calls);
    TEST_ASSERT_EQUAL_UINT(0, client.flush_calls);
    TEST_ASSERT_EQUAL_INT(1, client.connect(IPAddress(192, 0, 2, 1), 443));
    TEST_ASSERT_EQUAL_UINT(1, client.write(uint8_t(1)));
    client.stop();
    client.stop();
    TEST_ASSERT_EQUAL_UINT(2, client.stop_calls);
}

static void test_failed_connect_cleans_up_and_new_connect_can_retry() {
    for (unsigned variant = 0; variant < 2; ++variant) {
        now_ms = 0;
        DeadlineTLSClient client;
        client.arm();
        client.connect_result = 0;
        const int connected = variant == 0
            ? client.connect("example.invalid", 443)
            : client.connect(IPAddress(192, 0, 2, 1), 443);
        TEST_ASSERT_EQUAL_INT(0, connected);
        TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
        client.arm();
        TEST_ASSERT_EQUAL_UINT(0, client.write(uint8_t(1)));
        TEST_ASSERT_EQUAL_UINT(0, client.write_calls);
        client.connect_result = 1;
        TEST_ASSERT_EQUAL_INT(1, client.connect("example.invalid", 443));
        TEST_ASSERT_EQUAL_UINT(1, client.write(uint8_t(1)));
        TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    }
}

static void test_both_connect_overloads_recheck_deadline() {
    for (unsigned variant = 0; variant < 2; ++variant) {
        now_ms = 0;
        DeadlineTLSClient client;
        client.arm();
        client.connect_delay = 3000;
        const int connected = variant == 0
            ? client.connect("example.invalid", 443)
            : client.connect(IPAddress(192, 0, 2, 1), 443);
        TEST_ASSERT_EQUAL_INT(0, connected);
        TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
        TEST_ASSERT_EQUAL_UINT(1, client.host_connect_calls + client.ip_connect_calls);
        client.arm();
        TEST_ASSERT_EQUAL_UINT(0, client.write(uint8_t(1)));
        TEST_ASSERT_EQUAL_UINT(0, client.write_calls);
    }
}

static void test_read_budget_counts_prefetched_bytes_and_delivers_last_cache() {
    DeadlineTLSClient client;
    start_session(client);
    for (unsigned index = 0; index < 1025; ++index) {
        client.incoming.push_back(static_cast<uint8_t>(index % 251));
    }
    for (unsigned index = 0; index < 1024; ++index) {
        TEST_ASSERT_EQUAL_INT(1, client.available());
        TEST_ASSERT_EQUAL_INT(1, client.available());
        TEST_ASSERT_EQUAL_INT(static_cast<int>(index % 251), client.peek());
        TEST_ASSERT_EQUAL_UINT(index + 1, client.received_bytes);
        TEST_ASSERT_EQUAL_INT(static_cast<int>(index % 251), client.read());
    }
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_INT(-1, client.read());
    TEST_ASSERT_EQUAL_UINT(1024, client.received_bytes);
    TEST_ASSERT_EQUAL_UINT(1024, client.read_calls);
    TEST_ASSERT_EQUAL_UINT(1, client.incoming.size());
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    client.arm();
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_UINT(1024, client.received_bytes);
}

static void test_arm_restarts_healthy_time_and_read_budgets() {
    DeadlineTLSClient client;
    start_session(client);
    for (unsigned index = 0; index < 2047; ++index) client.incoming.push_back(0x61);
    for (unsigned index = 0; index < 1023; ++index) {
        TEST_ASSERT_EQUAL_INT(1, client.available());
        TEST_ASSERT_EQUAL_INT(0x61, client.read());
    }
    now_ms = 2999;
    client.arm();
    now_ms = 3000;
    TEST_ASSERT_EQUAL_UINT(1, client.write(uint8_t(1)));
    for (unsigned index = 0; index < 1024; ++index) {
        TEST_ASSERT_EQUAL_INT(1, client.available());
        TEST_ASSERT_EQUAL_INT(0x61, client.read());
    }
    TEST_ASSERT_EQUAL_UINT(2047, client.received_bytes);
    TEST_ASSERT_EQUAL_INT(0, client.available());
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);

    DeadlineTLSClient timed;
    now_ms = 0;
    start_session(timed);
    now_ms = 2999;
    timed.arm();
    now_ms = 5998;
    TEST_ASSERT_EQUAL_UINT(1, timed.write(uint8_t(1)));
    now_ms = 5999;
    TEST_ASSERT_EQUAL_UINT(0, timed.write(uint8_t(1)));
    TEST_ASSERT_EQUAL_UINT(1, timed.stop_calls);
}

static void test_uint32_millis_wrap_preserves_exact_deadline() {
    DeadlineTLSClient client;
    const uint32_t start = UINT32_MAX - uint32_t(1000);
    now_ms = start;
    start_session(client);
    now_ms = start + uint32_t(2999);
    TEST_ASSERT_EQUAL_UINT(1, client.write(uint8_t(1)));
    client.incoming.push_back(0x73);
    TEST_ASSERT_EQUAL_INT(1, client.available());
    now_ms = start + uint32_t(3000);
    TEST_ASSERT_EQUAL_INT(0x73, client.read());
    TEST_ASSERT_EQUAL_UINT(0, client.write(uint8_t(1)));
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
    TEST_ASSERT_EQUAL_UINT(1, client.write_calls);
    // Returning to an old clock value must not resurrect an observed fault.
    now_ms = start;
    client.arm();
    TEST_ASSERT_EQUAL_UINT(0, client.write(uint8_t(1)));
    TEST_ASSERT_EQUAL_UINT(1, client.write_calls);
}

static void test_buffer_read_respects_requested_size_and_canaries() {
    DeadlineTLSClient client;
    start_session(client);
    client.incoming = {0x11, 0x22, 0x33};
    uint8_t storage[] = {0xa5, 0xcc, 0xcc, 0xcc, 0x5a};
    TEST_ASSERT_EQUAL_INT(0, client.read(storage + 1, 0));
    TEST_ASSERT_EQUAL_UINT(0, client.received_bytes);
    TEST_ASSERT_EQUAL_INT(2, client.read(storage + 1, 2));
    const uint8_t expected[] = {0xa5, 0x11, 0x22, 0xcc, 0x5a};
    TEST_ASSERT_EQUAL_UINT8_ARRAY(expected, storage, sizeof(storage));
    TEST_ASSERT_EQUAL_UINT(2, client.received_bytes);
    TEST_ASSERT_EQUAL_UINT(1, client.incoming.size());
    TEST_ASSERT_EQUAL_INT(1, client.read(storage + 3, 1));
    TEST_ASSERT_EQUAL_HEX8(0x33, storage[3]);
    TEST_ASSERT_EQUAL_HEX8(0x5a, storage[4]);
}

static void test_buffer_read_delivers_cache_without_fabricating_ff_at_deadline() {
    DeadlineTLSClient client;
    start_session(client);
    client.incoming = {0x24, 0x35};
    now_ms = 2999;
    TEST_ASSERT_EQUAL_INT(1, client.available());
    now_ms = 3000;
    uint8_t storage[] = {0xa5, 0xcc, 0xcc, 0x5a};
    TEST_ASSERT_EQUAL_INT(1, client.read(storage + 1, 2));
    const uint8_t expected[] = {0xa5, 0x24, 0xcc, 0x5a};
    TEST_ASSERT_EQUAL_UINT8_ARRAY(expected, storage, sizeof(storage));
    TEST_ASSERT_EQUAL_UINT(1, client.received_bytes);
    TEST_ASSERT_EQUAL_UINT(1, client.incoming.size());
    TEST_ASSERT_EQUAL_UINT(1, client.stop_calls);
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_cached_byte_survives_available_read_deadline_race);
    RUN_TEST(test_available_crossing_deadline_stops_before_prefetch);
    RUN_TEST(test_prefetch_read_crossing_deadline_never_promises_a_byte);
    RUN_TEST(test_available_requires_a_real_byte_and_negative_read_latches_fault);
    RUN_TEST(test_short_write_arm_does_not_revive_but_connect_recovers);
    RUN_TEST(test_single_byte_short_write_stops_session);
    RUN_TEST(test_writes_recheck_deadline_after_base_call);
    RUN_TEST(test_connected_crossing_deadline_latches_fault);
    RUN_TEST(test_flush_rechecks_deadline_after_base_call);
    RUN_TEST(test_stop_is_idempotent_and_arm_cannot_revive_stopped_session);
    RUN_TEST(test_failed_connect_cleans_up_and_new_connect_can_retry);
    RUN_TEST(test_both_connect_overloads_recheck_deadline);
    RUN_TEST(test_read_budget_counts_prefetched_bytes_and_delivers_last_cache);
    RUN_TEST(test_arm_restarts_healthy_time_and_read_budgets);
    RUN_TEST(test_uint32_millis_wrap_preserves_exact_deadline);
    RUN_TEST(test_buffer_read_respects_requested_size_and_canaries);
    RUN_TEST(test_buffer_read_delivers_cache_without_fabricating_ff_at_deadline);
    return UNITY_END();
}
