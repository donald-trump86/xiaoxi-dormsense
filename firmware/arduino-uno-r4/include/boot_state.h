#ifndef XIAOXI_BOOT_STATE_H
#define XIAOXI_BOOT_STATE_H
#include <cstdint>

constexpr uint32_t BOOT_MAGIC = 0x58585331U;
struct BootRecord { uint32_t magic; uint32_t counter; uint32_t inverse; };

inline bool next_boot(const BootRecord& previous, BootRecord& next) {
    const bool erased = previous.magic == UINT32_MAX &&
        previous.counter == UINT32_MAX && previous.inverse == UINT32_MAX;
    if (!erased && (previous.magic != BOOT_MAGIC ||
        previous.inverse != ~previous.counter || previous.counter == UINT32_MAX))
        return false;
    const uint32_t counter = erased ? 1U : previous.counter + 1U;
    next = {BOOT_MAGIC, counter, ~counter};
    return true;
}

inline uint32_t next_backoff(uint32_t delay_ms) {
    return delay_ms >= 30000U ? 60000U : delay_ms * 2U;
}

// 4-pin LM393 LDR module on 5V/10-bit ADC (A0): pull-up to VCC, LDR to GND.
// Lower ADC voltage means brighter light; normalize to [0.000, 1.000].
inline bool normalize_ldr_adc(int raw_adc, float& light_ratio) {
    if (raw_adc < 0 || raw_adc > 1023) return false;
    light_ratio = static_cast<float>(1023 - raw_adc) / 1023.0f;
    return true;
}
#endif
