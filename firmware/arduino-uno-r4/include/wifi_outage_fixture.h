#ifndef XIAOXI_WIFI_OUTAGE_FIXTURE_H
#define XIAOXI_WIFI_OUTAGE_FIXTURE_H

// Hardware fault fixture ONLY, opt-in via the dedicated PIO environment.
// Disconnect this UNO, never the Mac/router. Suppress application reconnect for
// 45 seconds, keep UART sampling/sequence allocation, then use normal recovery.
// A status observation proves a link-down instant, not 45s of physical outage.
inline bool wifi_outage_fixture(uint32_t generated, bool& online,
                               DeadlineTLSClient& client, void (*purge)()) {
    static bool active = false, finished = false, saw_down = false;
    static uint32_t started = 0;
    if (active) {
        if (!saw_down) {
            const int status = WiFi.status();
            if (status != WL_CONNECTED) {
                saw_down = true;
                Serial.print("wifi_fixture_disconnected_status=");
                Serial.println(status);
            }
        }
        if (uint32_t(millis() - started) < 45000U) return true;
        active = false;
        finished = true;
        Serial.println("wifi_fixture_resume=true");
    }
    if (!finished && online && generated >= 3U) {
        client.arm();
        client.stop();
        online = false;
        const int accepted = WiFi.disconnect();
        purge();
        started = millis();
        active = true;
        Serial.print("wifi_fixture_request_accepted=");
        Serial.println(accepted);
        return true;
    }
    return false;
}
#endif
