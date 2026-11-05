#pragma once
#include <cstddef>
#include <cstdint>

// Include after WiFiS3.h (or the host test double). 3000ms is an admission
// budget, not a hard wall-clock deadline: an in-flight finite modem call and
// stop can add a tail. Every return from that call is checked before use.
class DeadlineTLSClient : public WiFiSSLClient {
public:
    void arm() { started_ = millis(); remaining_ = 1024; }
    int connect(const char* host, uint16_t port) override {
        // Never reuse a stream that may contain an incomplete MQTT packet.
        stop();
        faulted_ = false;
        closed_ = false;
        if (!check()) return 0;
        const int result = WiFiSSLClient::connect(host, port);
        if (!check() || result != 1) { stop(); return 0; }
        return 1;
    }
    int connect(IPAddress ip, uint16_t port) override {
        return connect(ip.toString().c_str(), port);
    }
    size_t write(uint8_t byte) override { return write(&byte, 1); }
    size_t write(const uint8_t* bytes, size_t size) override {
        if (!check()) return 0;
        const size_t result = WiFiSSLClient::write(bytes, size);
        if (!check() || result != size) { stop(); return 0; }
        return result;
    }
    int available() override {
        // Honor a previously promised byte, even just after the deadline.
        if (cached_ >= 0) return 1;
        if (!check()) return 0;
        const int count = WiFiSSLClient::available();
        if (!check()) return 0;
        if (count < 0) { stop(); return 0; }
        if (count == 0) return 0;
        uint8_t byte = 0;
        const int result = WiFiSSLClient::read(&byte, 1);
        if (!check()) return 0;
        if (result != 1) { stop(); return 0; }
        --remaining_;
        cached_ = byte;
        return 1;
    }
    int read() override {
        if (cached_ < 0 && !available()) return -1;
        const int byte = cached_;
        cached_ = -1;
        return byte;
    }
    int read(uint8_t* bytes, size_t size) override {
        size_t count = 0;
        while (count < size && available()) {
            const int byte = read();
            if (byte < 0) break;
            bytes[count++] = static_cast<uint8_t>(byte);
        }
        return static_cast<int>(count);
    }
    int peek() override { return available() ? cached_ : -1; }
    void flush() override {
        if (check()) { WiFiSSLClient::flush(); check(); }
    }
    uint8_t connected() override {
        if (!check()) return 0;
        const uint8_t result = WiFiSSLClient::connected();
        return check() ? result : 0;
    }
    void stop() override {
        faulted_ = true;
        cached_ = -1;
        if (!closed_) {
            closed_ = true; // Set before the underlying call.
            WiFiSSLClient::stop();
        }
    }
private:
    bool check() {
        if (faulted_) return false;
        if (uint32_t(millis() - started_) >= 3000U || remaining_ == 0) {
            stop();
            return false;
        }
        return true;
    }
    uint32_t started_ = 0;
    unsigned remaining_ = 1024;
    int cached_ = -1;
    bool closed_ = true;
    bool faulted_ = true;
};
