#ifndef XIAOXI_SHT31_UART_H
#define XIAOXI_SHT31_UART_H

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>

// Fixed-memory ASCII parser; no Arduino/network dependencies.
// Use accessors only after fresh(now) succeeds. While no new frame arrives,
// poll fresh at least every 5000ms, or reset before an unbounded polling gap.
// A uint32 timestamp alone cannot distinguish elapsed whole clock cycles.
// Expiration is latched so a reading observed to be stale cannot resurrect.
class Sht31Parser {
public:
    bool feed(char byte, uint32_t now_ms) {
        if (byte == '\n') {
            bool accepted = false;
            if (!discarding_ && length_ > 0 && line_[length_ - 1] == '\r') {
                line_[--length_] = '\0';
                accepted = parse_line(now_ms);
            }
            length_ = 0;
            discarding_ = false;
            return accepted;
        }
        if (discarding_) return false;
        const unsigned char value = static_cast<unsigned char>(byte);
        if ((byte != '\r' && (value < 32 || value > 126)) ||
            length_ >= sizeof(line_) - 1) {
            discarding_ = true;
            return false;
        }
        line_[length_++] = byte;
        return false;
    }

    void reset() {
        length_ = 0;
        discarding_ = false;
        valid_ = false;
    }

    bool fresh(uint32_t now_ms) const {
        if (valid_ && static_cast<uint32_t>(now_ms - last_frame_ms_) > 5000U) {
            valid_ = false;
        }
        return valid_;
    }

    float temperature() const { return temperature_; }
    float humidity() const { return humidity_; }

private:
    // Observed wire grammar: decimal integer part, one fractional digit;
    // temperature may be negative. No whitespace, exponents, NaN/Inf, or '+'.
    static bool decimal(const char* text, std::size_t size,
                        bool allow_negative, float& result) {
        std::size_t index = 0;
        bool negative = false;
        if (size && text[0] == '-') {
            if (!allow_negative) return false;
            negative = true;
            ++index;
        }
        const std::size_t digits_start = index;
        float value = 0;
        while (index < size && text[index] >= '0' && text[index] <= '9') {
            value = value * 10.0f + static_cast<float>(text[index] - '0');
            ++index;
        }
        if (index == digits_start || index + 2 != size || text[index] != '.' ||
            text[index + 1] < '0' || text[index + 1] > '9') return false;
        value += static_cast<float>(text[index + 1] - '0') / 10.0f;
        if (!std::isfinite(value)) return false;
        result = negative ? -value : value;
        return true;
    }

    bool parse_line(uint32_t now_ms) {
        if (length_ < 2 || line_[0] != 'R' || line_[1] != ':' ||
            line_[length_ - 1] != 'C') return false;
        const char* separator = std::strstr(line_ + 2, "RH ");
        if (!separator) return false;
        const char* temperature_start = separator + 3;
        const char* temperature_end = line_ + length_ - 1;
        if (temperature_start >= temperature_end) return false;
        float humidity = 0;
        float temperature = 0;
        if (!decimal(line_ + 2, static_cast<std::size_t>(separator - line_ - 2),
                     false, humidity) || humidity < 0 || humidity > 100 ||
            !decimal(temperature_start,
                     static_cast<std::size_t>(temperature_end - temperature_start),
                     true, temperature)) return false;
        humidity_ = humidity;
        temperature_ = temperature;
        last_frame_ms_ = now_ms;
        valid_ = true;
        return true;
    }

    char line_[64] = {};
    std::size_t length_ = 0;
    bool discarding_ = false;
    mutable bool valid_ = false;
    uint32_t last_frame_ms_ = 0;
    float temperature_ = 0;
    float humidity_ = 0;
};

#endif
