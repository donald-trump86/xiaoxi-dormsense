# ESP32-C3 红外学习与回放固件（`node02`）

本目录包含宿舍空调红外波形学习与受控回放节点（`node02`）的 PlatformIO 工程、离线时序分析工具及单元测试套件。

---

## 1. 模块架构与核心特性

针对宿舍格力空调原装遥控器发送的 **280 边沿双段长帧（128-bit）**，固件在标准 `IRremoteESP8266`（v2.9.0）解码基础上实现了 `learn1` 原始微秒脉冲采集与一次性挑战码（Challenge-Commit）回放协议：

| 文件路径 | 模块职责与实现说明 |
| --- | --- |
| [include/ir_node_logic.h](include/ir_node_logic.h) | 基础命令参数校验、11 种开源空调协议映射与 최근 8 个 `command_id` 的环形缓冲去重 |
| [include/ir_raw_timing.h](include/ir_raw_timing.h) | 将 `IRrecv` 捕获的 `2 μs` tick 数组转换为每包最多 16 项、最高 300 项的 `ir_raw_timing` 微秒分包文本 |
| [include/ir_learning.h](include/ir_learning.h) | `learn1` 五类动作（`ir_status`、`ir_learn_start`、`ir_learn_cancel`、`ir_raw_prepare`、`ir_raw_commit`）严格 JSON 校验、单调时钟 `deadline_ms` 检查与 10 秒一次性挑战码状态机 |
| [include/ir_learning_capture.h](include/ir_learning_capture.h) | 将 `IRGreeAC` / `IRKelvinatorAC` 解码结果归一化为 14 个标准空调状态字段（`power, mode, temp_c, fan, swingv, swingh, light, turbo, econo, clean, sleep, filter, quiet, ifeel`），对不支持的字段保留 `null` |
| [src/main.cpp](src/main.cpp) | 主程序：默认被动静默启动（不自动发射红外）；在执行 `ir_raw_commit` 或 `ac_send` 发射期间自动调用 `irrecv.disableIRIn()` 暂停 GPIO4 接收中断，避免单核自发自收中断抢占，发射完毕后恢复监听 |
| [tools/nec_timing.py](tools/nec_timing.py) | 宿主机离线脉冲重组与 NEC 协议窗口比对工具，支持从事件 JSON 中还原微秒数组并定位超差脉冲 |

---

## 2. 本地测试、编译与烧录

工程提供两套互补的自动化测试：**PlatformIO native 测试**（测试纯头文件逻辑）与**宿主机 Python+C++ 联合测试**（直接编译链接 `IRremoteESP8266` 源码验证真实编解码与回放流程）：

```bash
# 1. 复制本地私钥配置模板（首次初始化）
cp firmware/esp32-c3-ir/include/secrets.example.h firmware/esp32-c3-ir/include/secrets.h

# 2. 运行 13 项 PlatformIO native 单元测试
pio test -d firmware/esp32-c3-ir -e native

# 3. 运行 22 项宿主机固件与脉冲时序分析测试
source .venv/bin/activate
python -m unittest discover -s firmware/esp32-c3-ir/test -p 'test_*.py' -v

# 4. 编译 ESP32-C3 固件镜像（依赖固定为 IRremoteESP8266@2.9.0、PubSubClient@2.8.0、ArduinoJson@7.2.1）
pio run -d firmware/esp32-c3-ir -e esp32c3

# 5. 连接 ESP32-C3 后烧录固件
pio run -d firmware/esp32-c3-ir -e esp32c3 -t upload
```

完整 `learn1` 通信协议与逐键学习流程请参考 [MQTT 协议文档](../../docs/mqtt-protocol.md) 与 [空调波形学习指南](../../docs/ac-onboarding.md)。
