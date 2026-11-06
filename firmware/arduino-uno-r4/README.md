# Arduino UNO R4 WiFi 感知陪伴固件（`node01`）

本目录包含宿舍环境感知与桌面点阵陪伴节点（`node01`）的 PlatformIO 工程与 native 单元测试。

---

## 1. 核心功能与源码模块

固件将与硬件无关的帧解析、启动计数、点阵动画和状态机抽离在 `include/` 头文件中，主程序 `src/main.cpp` 负责串口、ADC、LED 矩阵与 MQTT TLS 网络调度：

| 文件路径 | 模块职责与关键算法 |
| --- | --- |
| [include/sht31_uart.h](include/sht31_uart.h) | SHT31 串口模组（9600 8N1）字节流状态机，支持跨主循环周期拼接被切分的 `\r\n` 帧并校验温湿度物理量程 |
| [include/boot_state.h](include/boot_state.h) | 基于片上 EEPROM 的掉电递增启动计数器，生成全局唯一的 `boot_id`（如 `node01-00000009`） |
| [include/led_companion.h](include/led_companion.h) | 板载 12×8 LED 矩阵五幕陪伴像素动画（笑脸、温度计、水滴、灯泡、暗光睡眠 `Zzz`、声波跳动）、3×5 数字字模与三线按钮手势状态机 |
| [include/deadline_tls.h](include/deadline_tls.h) | 带单调时钟超时保护的 TLS Socket 包装器，防止 Wi-Fi 抖动时握手或写缓冲无限阻塞主循环 |
| [include/wifi_outage_fixture.h](include/wifi_outage_fixture.h) | 断网重连与状态恢复逻辑验证辅助头文件 |
| [src/main.cpp](src/main.cpp) | 硬件驱动入口：每 10 秒上报一帧 TLS 8883 遥测，并在每次 `analogRead(A0)` 前消隐 Port 0/2 点阵引脚、调用 `R_BSP_PinAccessEnable()` 解除 RA4M1 `PWPR` 寄存器锁冲突 |

---

## 2. 本地测试、编译与烧录

```bash
# 1. 复制本地连接配置模板（首次初始化，填写后再编译）
cp firmware/arduino-uno-r4/include/secrets.example.h firmware/arduino-uno-r4/include/secrets.h

# 2. 在宿主机运行 39 项 PlatformIO native 单元测试（无需连接开发板）
pio test -d firmware/arduino-uno-r4 -e native

# 3. 交叉编译 UNO R4 WiFi 固件镜像
pio run -d firmware/arduino-uno-r4 -e uno_r4_wifi

# 4. 连接开发板后烧录固件
pio run -d firmware/arduino-uno-r4 -e uno_r4_wifi -t upload
```

硬件引脚接线与双板单口串联供电方法详见 [硬件指南](../../docs/hardware.md)。
