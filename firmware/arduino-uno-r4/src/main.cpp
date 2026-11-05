#include <Arduino.h>
#include <Arduino_LED_Matrix.h>
#include <EEPROM.h>
#include <WiFiS3.h>
#include <PubSubClient.h>
#include <cstdio>
#include <cstring>
#include "boot_state.h"
#include "led_companion.h"
#include "sht31_uart.h"
#include "secrets.h"

#include "deadline_tls.h"
#ifdef XIAOXI_WIFI_OUTAGE_TEST
#include "wifi_outage_fixture.h"
#endif

Sht31Parser sensor;
ArduinoLEDMatrix matrix;
DeadlineTLSClient transport;
PubSubClient mqtt(transport);
constexpr char TELEMETRY_TOPIC[] = "xiaoxi/dorm/node01/telemetry";
constexpr char STATUS_TOPIC[] = "xiaoxi/dorm/node01/status";
constexpr char EVENT_TOPIC[] = "xiaoxi/dorm/node01/event";
constexpr uint8_t BUTTON_PINS[3] = {2, 3, 4};  // D2, D3, D4 unmarked 3-wire button
constexpr char OFFLINE[] = "{\"schema_version\":\"1.0\",\"node_id\":\"node01\",\"state\":\"offline\"}";
constexpr char ONLINE[] = "{\"schema_version\":\"1.0\",\"node_id\":\"node01\",\"state\":\"online\"}";
char boot_id[24] = {};
uint32_t sequence = 0;
uint32_t last_sample = 0;
uint32_t last_network = 0;
uint32_t last_matrix = 0;
uint32_t boot_started_at = 0;
uint32_t last_publish_ok_at = 0;
bool have_publish_ok = false;
uint32_t last_retry = 0;
uint32_t retry_ms = 0;
bool online = false;
bool fatal = false;
char raw_line[64] = {};
unsigned raw_length = 0;
uint32_t uart_empty_at = 0;
uint32_t frame_lower_bound = 0;

void clear_uart() {
    sensor.reset();
    raw_length = 0;
    while (true) {
        // Timestamp BEFORE observing an empty FIFO; a byte arriving just after
        // this observation cannot have an earlier completion time.
        const uint32_t checked_at = millis();
        if (Serial1.available() <= 0) { uart_empty_at = checked_at; break; }
        Serial1.read();
    }
    // A leftover partial suffix is rejected by the strict parser. Only a new
    // complete frame can become valid after a handshake.
}

void receive_sensor() {
    const uint32_t now = millis();
    // Reset after long gaps within one uint32 cycle or stale partial frames.
    // Full-cycle/unbounded suspensions require reset BEFORE the suspension.
    // Dropping uncertain frames is intentionally conservative.
    if (uint32_t(now - uart_empty_at) >= 5000U ||
        (raw_length && uint32_t(now - frame_lower_bound) >= 5000U)) {
        clear_uart();
        return;
    }
    while (true) {
        const uint32_t checked_at = millis();
        if (Serial1.available() <= 0) { uart_empty_at = checked_at; break; }
        const int value = Serial1.read();
        if (value < 0) break;
        const char byte = static_cast<char>(value);
        // Keep the first-byte bound across fragmented CRLF and empty polls.
        if (raw_length == 0) frame_lower_bound = uart_empty_at;
        if (raw_length < sizeof(raw_line) - 1) raw_line[raw_length++] = byte;
        const bool valid = sensor.feed(byte, frame_lower_bound);
        if (byte == '\n') {
            unsigned length = raw_length;
            while (length && (raw_line[length - 1] == '\r' || raw_line[length - 1] == '\n')) --length;
            raw_line[length] = '\0';
            if (valid) { Serial.print("UART "); Serial.println(raw_line); }
            raw_length = 0;
        }
    }
    sensor.fresh(millis());
}

void finish_network(uint32_t started, bool handshake) {
    const uint32_t elapsed = millis() - started;
    if (handshake || elapsed >= 5000U) clear_uart();
    else receive_sensor();
    if (elapsed >= 500U) {
        Serial.print("network_op_ms="); Serial.println(elapsed);
    }
}

bool allocate_boot() {
    BootRecord previous = {}, next = {}, verified = {};
    EEPROM.get(0, previous);
    if (!next_boot(previous, next)) return false;
    EEPROM.put(0, next);
    EEPROM.get(0, verified);
    if (std::memcmp(&next, &verified, sizeof(next)) != 0) return false;
    std::snprintf(boot_id, sizeof(boot_id), "node01-%08lx", static_cast<unsigned long>(next.counter));
    sequence = 0;
    Serial.print("boot_id="); Serial.println(boot_id);
    return true;
}

void retry_later() {
    last_retry = millis();
    retry_ms = retry_ms == 0 ? 1000U : next_backoff(retry_ms);
    Serial.print("retry_ms="); Serial.println(retry_ms);
}

void network_task() {
#ifdef XIAOXI_WIFI_OUTAGE_TEST
    const uint32_t fixture_started = millis();
    const bool held = wifi_outage_fixture(sequence, online, transport, clear_uart);
    finish_network(fixture_started, false);
    if (held) return;
#endif
    uint32_t started = millis();
    int status = WiFi.status();
    finish_network(started, false);
    if (status != WL_CONNECTED) {
        if (online) {
            started = millis(); transport.arm(); transport.stop();
            finish_network(started, true); online = false;
            Serial.println("network_offline=true");
        }
        if (uint32_t(millis() - last_retry) < retry_ms) return;
        clear_uart();
        started = millis();
        status = WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        finish_network(started, true);
        Serial.print("wifi_status="); Serial.println(status);
        if (status != WL_CONNECTED) { retry_later(); return; }
        started = millis();
        Serial.print("wifi_connected=true; local_ip="); Serial.println(WiFi.localIP());
        finish_network(started, true);
        retry_ms = 0;
    }
    if (!online) {
        if (uint32_t(millis() - last_retry) < retry_ms) return;
        clear_uart();
        started = millis(); transport.arm();
        // Stable per-node client ID forces old-session takeover before new online;
        // boot_id belongs in payloads, not concurrent retained-LWT sessions.
        const bool connected = mqtt.connect("xiaoxi-node01", MQTT_USERNAME, MQTT_PASSWORD,
                                             STATUS_TOPIC, 1, true, OFFLINE, true);
        online = connected && mqtt.publish(STATUS_TOPIC, ONLINE, true);
        if (!online) transport.stop();
        finish_network(started, true);
        Serial.print("mqtt_connected="); Serial.println(online ? "true" : "false");
        Serial.print("mqtt_state="); Serial.println(mqtt.state());
        if (online) retry_ms = 0; else retry_later();
    } else {
        started = millis(); transport.arm();
        online = mqtt.loop();
        if (!online) transport.stop();
        finish_network(started, false);
        if (!online) retry_later();
    }
}

float cached_light_ratio = 0.0f;
bool cached_light_ok = false;

int sample_ldr_adc() {
    __disable_irq();
    R_PORT0->PCNTR1 &= ~((uint32_t)LED_MATRIX_PORT0_MASK);
    R_PORT2->PCNTR1 &= ~((uint32_t)LED_MATRIX_PORT2_MASK);
    delayMicroseconds(15);
    (void)analogRead(A0);
    int sum = 0;
    for (int index = 0; index < 4; ++index) sum += analogRead(A0);
    R_BSP_PinAccessEnable();
    __enable_irq();
    const int avg = (sum + 2) / 4;
    cached_light_ok = normalize_ldr_adc(avg, cached_light_ratio);
    return avg;
}

void generate_sample(uint32_t periods) {
    if (periods > UINT32_MAX - 1U - sequence) {
        if (!allocate_boot()) { fatal = true; Serial.println("fatal=boot_counter_failure"); return; }
    } else sequence += periods - 1U;
    const bool valid = sensor.fresh(millis());
    char temperature[64] = "null", humidity[64] = "null";
    if (valid) {
        std::snprintf(temperature, sizeof(temperature), "%.1f", double(sensor.temperature()));
        std::snprintf(humidity, sizeof(humidity), "%.1f", double(sensor.humidity()));
    }
    const int raw_adc = sample_ldr_adc();
    float light_ratio = 0.0f;
    const bool light_valid = normalize_ldr_adc(raw_adc, light_ratio);
    char light[32] = "null";
    if (light_valid) {
        std::snprintf(light, sizeof(light), "%.3f", double(light_ratio));
    }
    Serial.print("adc_a0="); Serial.println(raw_adc);
    char payload[768];
    const int size = std::snprintf(payload, sizeof(payload),
        "{\"schema_version\":\"1.0\",\"node_id\":\"node01\",\"boot_id\":\"%s\","
        "\"timestamp\":null,\"sequence\":%lu,\"simulated\":false,"
        "\"temperature\":%s,\"humidity\":%s,\"light\":%s,"
        "\"sensor_status\":{\"temperature\":\"%s\",\"humidity\":\"%s\",\"light\":\"%s\"}}",
        boot_id, static_cast<unsigned long>(sequence), temperature, humidity, light,
        valid ? "ok" : "error", valid ? "ok" : "error", light_valid ? "ok" : "error");
    ++sequence; // Generated samples count even while disconnected. No backlog.
    if (size <= 0 || static_cast<unsigned>(size) >= sizeof(payload)) {
        Serial.println("sample_error=buffer_limit"); return;
    }
    Serial.println(payload);
    bool sent = false;
    if (online) {
        const uint32_t started = millis(); transport.arm();
        sent = mqtt.publish(TELEMETRY_TOPIC, payload, false); // Library publishes QoS0.
        if (!sent) { transport.stop(); online = false; retry_later(); }
        finish_network(started, false);
    }
    if (sent) {
        last_publish_ok_at = millis();
        have_publish_ok = true;
    }
    Serial.print("telemetry_transmitted="); Serial.println(sent ? "true" : "false");
}

uint32_t last_frame_words[3] = {0xFFFFFFFFU, 0xFFFFFFFFU, 0xFFFFFFFFU};
xiaoxi::led::ButtonGestureTracker button_tracker;
uint32_t last_button_scan = 0;
uint32_t voice_mode_until = 0;
uint8_t manual_scene_offset = 0;
uint32_t event_sequence = 0;

uint8_t last_debug_mask = 0xFFu;

uint8_t scan_button_3wire() {
    uint8_t mask = 0;
    uint8_t bit = 0;
    for (uint8_t low_idx = 0; low_idx < 3; ++low_idx) {
        for (uint8_t sense_idx = 0; sense_idx < 3; ++sense_idx) {
            if (sense_idx == low_idx) continue;
            const uint8_t float_idx = static_cast<uint8_t>(3U - low_idx - sense_idx);
            pinMode(BUTTON_PINS[float_idx], INPUT);
            pinMode(BUTTON_PINS[sense_idx], INPUT_PULLUP);
            pinMode(BUTTON_PINS[low_idx], OUTPUT);
            digitalWrite(BUTTON_PINS[low_idx], LOW);
            delayMicroseconds(20);
            if (digitalRead(BUTTON_PINS[sense_idx]) == HIGH) {
                mask |= static_cast<uint8_t>(1u << bit);
            }
            ++bit;
        }
    }
    for (uint8_t i = 0; i < 3; ++i) {
        pinMode(BUTTON_PINS[i], INPUT_PULLUP);
    }
    R_BSP_PinAccessEnable();
    return mask;
}

void calibrate_button_3wire() {
    for (uint8_t i = 0; i < 3; ++i) {
        pinMode(BUTTON_PINS[i], INPUT_PULLUP);
    }
    delay(10);
    uint8_t mask = 0;
    for (uint8_t sample = 0; sample < 8; ++sample) {
        mask |= scan_button_3wire();
        delay(2);
    }
    button_tracker.init(mask);
    last_debug_mask = mask;
    Serial.print("button_baseline_mask=0x");
    Serial.println(mask, HEX);
}

void publish_button_event(const char* event_type, const char* detail) {
    char payload[384];
    const int n = std::snprintf(
        payload, sizeof(payload),
        "{\"schema_version\":\"1.0\",\"node_id\":\"node01\",\"boot_id\":\"%s\","
        "\"timestamp\":null,\"sequence\":%lu,\"simulated\":false,"
        "\"event_type\":\"%s\",\"severity\":\"info\",\"detail\":\"%s\"}",
        boot_id, static_cast<unsigned long>(event_sequence++), event_type, detail);
    if (n > 0 && static_cast<unsigned>(n) < sizeof(payload)) {
        Serial.println(payload);
        if (online) {
            const uint32_t started = millis();
            transport.arm();
            (void)mqtt.publish(EVENT_TOPIC, payload, false);
            finish_network(started, false);
        }
    }
}

void update_companion_matrix(uint32_t now) {
    const bool sht_ok = sensor.fresh(now) || (uint32_t(now - boot_started_at) < 3000U);
    const bool publish_flash = have_publish_ok && (uint32_t(now - last_publish_ok_at) < 800U);
    const bool voice_active = (voice_mode_until != 0) && (int32_t(voice_mode_until - now) > 0);
    const xiaoxi::led::CompanionInput input = {
        online,
        sht_ok,
        cached_light_ok,
        sensor.fresh(now) ? sensor.temperature() : 0.0f,
        sensor.fresh(now) ? sensor.humidity() : 0.0f,
        cached_light_ratio,
        publish_flash,
        voice_active,
        manual_scene_offset,
    };
    uint32_t frame_words[3] = {0, 0, 0};
    (void)xiaoxi::led::render_companion_frame(input, now, frame_words);
    if (std::memcmp(frame_words, last_frame_words, sizeof(frame_words)) != 0) {
        std::memcpy(last_frame_words, frame_words, sizeof(frame_words));
        matrix.loadFrame(frame_words);
        R_BSP_PinAccessEnable();
    }
}

void poll_button(uint32_t now) {
    const uint8_t mask = scan_button_3wire();
    if (mask != last_debug_mask) {
        last_debug_mask = mask;
        Serial.print("button_raw_mask=0x");
        Serial.print(mask, HEX);
        Serial.print(" base=0x");
        Serial.println(button_tracker.baseline_mask, HEX);
    }
    const xiaoxi::led::ButtonGesture g = button_tracker.update(mask, now);
    if (g == xiaoxi::led::BUTTON_GESTURE_NONE) return;
    char detail[96];
    std::snprintf(detail, sizeof(detail), "d2_d3_d4_mask=0x%02X changed=0x%02X",
                  mask, button_tracker.last_changed_mask);
    if (g == xiaoxi::led::BUTTON_GESTURE_SINGLE_PRESS) {
        Serial.print("button_gesture=single_press ");
        Serial.println(detail);
        if (voice_mode_until != 0 && int32_t(voice_mode_until - now) > 0) {
            voice_mode_until = 0;
        } else {
            ++manual_scene_offset;
        }
        update_companion_matrix(now);
        publish_button_event("button_single_press", detail);
    } else if (g == xiaoxi::led::BUTTON_GESTURE_DOUBLE_PRESS) {
        Serial.print("button_gesture=double_press ");
        Serial.println(detail);
        publish_button_event("button_double_press", detail);
    } else if (g == xiaoxi::led::BUTTON_GESTURE_LONG_PRESS) {
        Serial.print("button_gesture=long_press ");
        Serial.println(detail);
        voice_mode_until = now + 10000UL;
        update_companion_matrix(now);
        publish_button_event("button_long_press_voice", detail);
    }
}

void setup() {
    Serial.begin(115200);
    Serial1.begin(9600, SERIAL_8N1);
    (void)sample_ldr_adc();
    calibrate_button_3wire();
    matrix.begin();
    R_BSP_PinAccessEnable();
    boot_started_at = millis();
    update_companion_matrix(boot_started_at);
    modem.noDebug(); // Modem debug can include plaintext Wi-Fi requests.
    if (!allocate_boot()) { fatal = true; Serial.println("fatal=boot_counter_failure"); return; }
    modem.begin();
    modem.timeout(1500);
    WiFi.setTimeout(3000);
    transport.setConnectionTimeout(1500);
    transport.setCACert(MQTT_CA);
    mqtt.setServer(MQTT_HOST, 8883);
    mqtt.setKeepAlive(30);
    mqtt.setSocketTimeout(1);
    if (!mqtt.setBufferSize(1280)) { fatal = true; Serial.println("fatal=mqtt_buffer_allocation"); return; }
    Serial.print("modem_firmware="); Serial.println(WiFi.firmwareVersion());
    clear_uart();
    last_sample = millis();
    last_matrix = last_sample;
    Serial.println("wireless_probe_ready=true; simulated=false; control_disabled=true");
}

void loop() {
    if (fatal) { delay(10); return; }
    receive_sensor();
    uint32_t now = millis();
    if (uint32_t(now - last_button_scan) >= 12U) {
        last_button_scan = now;
        poll_button(now);
    }
    now = millis();
    if (uint32_t(now - last_matrix) >= 250U) {
        if (uint32_t(now - last_matrix) >= 250U && ((now / 250U) % 4U == 0U)) {
            (void)sample_ldr_adc();
        }
        last_matrix = now;
        update_companion_matrix(now);
    }
    now = millis();
    const uint32_t periods = uint32_t(now - last_sample) / 10000U;
    if (periods) { last_sample += periods * 10000U; generate_sample(periods); }
    now = millis();
    if (uint32_t(now - last_network) >= 731U) { last_network = now; network_task(); }
    delay(1);
}
