# UNO R4 WiFi 固件

本目录整理自私有实验 `experiments-private/real-sht31-wifi/firmware/`：运行源码、五个头文件和两组 native 测试保持原样。此次只建立正式源码与构建基线，不代表这份最新 UNO 源码已经烧录，也没有重新验收硬件、网络或完整系统。

使用 PlatformIO Core，可配合 VSCodium 扩展。UNO R4 与 ESP32-C3 分属 Renesas 与 Espressif 两套核心，隔离的工具链更不易搞混，依赖随 [platformio.ini](platformio.ini) 版本化。实际平台为 `platformio/renesas-ra@1.9.0`，board 为 `uno_r4_wifi`，Arduino Renesas 核心固定为已安装的 `1.6.0`，PubSubClient 为 `2.8.0`；native 为 `1.2.1`，Unity 为 `2.6.1`。版本来自实验配置及本机依赖元数据；参见[硬件说明](../../docs/hardware.md)。这些固定项不是全部传递工具依赖的锁文件。

## 当前源码行为

- 使用 `Serial1`、9600 baud、8N1 读取 SHT31 **UART 模组**的 ASCII 帧，不是裸 SHT31 的 I²C 驱动。A0 光敏读数归一化为 `light`，不是 lux。未知型号、供电和接线仍须先确认，不能把此配置套到不同传感器上。
- node01 每 10 秒发送遥测，缺测通道为 `null`，未同步时间为 `null`，真实采样标记 `simulated=false`；遵循 [MQTT v1 遥测约定](../../docs/mqtt-protocol.md)。按钮事件和 LED 状态也已包含在本源码中。
- D2/D3/D4 三线按钮在启动时采集基线；A0 采样暂时关闭矩阵扫描以减少干扰。单击换场景，双击发事件，长按给出 10 秒视觉模式并发事件；没有语音采集或语音服务。
- PubSubClient 发布为 QoS 0，保留状态，LWT 为 QoS 1，clean session 开启；不承诺库不支持的 QoS 1 发布。网络重试有退避，UART 在握手与间隔后清理；TLS 包装器的 3 秒预算是调用准入限制，不能强行中断底层阻塞调用。
- `uno_r4_wifi_outage_test` 仅为显式选择的故障夹具：累计三次样本后让本 UNO 断开 Wi-Fi 45 秒。正常环境不定义该测试宏。

## 首次构建

安装 PlatformIO Core 和本机 C++ 编译器后，在仓库根目录执行下列命令。首次解析依赖需要下载所固定的平台和库；这里的命令只构建，不包含烧录或串口访问。

```bash
cd firmware/arduino-uno-r4
pio test -e native
cp -n include/secrets.example.h include/secrets.h
# 在本机编辑 include/secrets.h，替换全部占位值后再构建：
pio run -e uno_r4_wifi
```

凭据只写入已忽略的 `include/secrets.h`，模板是 [secrets.example.h](include/secrets.example.h)。必须填写 `WIFI_SSID`、`WIFI_PASSWORD`、`MQTT_HOST`、`MQTT_USERNAME`、`MQTT_PASSWORD` 和受信 Broker CA PEM `MQTT_CA`；主机须与证书匹配，端口固定为 8883。模板的 `.invalid` 主机和 CA 占位内容不可用于连接。源码直接包含 `secrets.h`，不会自动退回模板；native 测试不需要凭据。不要硬编码真实 SSID/密码、把个人宿舍信息写入 node_id，或接入高风险执行器。

## 测试边界

[test_uart](test/test_uart/test_main.cpp) 覆盖严格 UART 帧解析、过期/溢出、启动计数、退避、归一化和 LED/按钮逻辑；[test_transport](test/test_transport/test_main.cpp) 使用假时钟与假 TLS 客户端检查预算、短读写和断开状态。两组均为合成的离线测试，不会发布遥测。通过 native 测试不证明传感器精度、接线、TLS 连通、矩阵 ADC 干扰或掉线恢复已在硬件上重新验证。

2026-11-05 正式目录验证：`pio test -e native` 34/34 通过，`pio run -e uno_r4_wifi` 构建通过。构建临时使用模板中的假配置，验证后已删除；占用 Flash 68,932 B、RAM 6,808 B，这些大小对应占位配置，不作为生产二进制大小或已烧录证明。没有执行 upload、串口连接或断网夹具。
