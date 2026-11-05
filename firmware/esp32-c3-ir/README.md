# ESP32-C3 红外节点固件

本目录整理自私有实验 `experiments-private/real-sht31-wifi/firmware-esp32c3/`，保留运行源码和协议允许列表。两份测试随源码保留：Unity 测试补齐空的 setup/teardown 钩子，离线 AC handler 测试增加已有库目录的可选环境变量。没有复制上游库、构建产物、私密配置或日志。

[src/main.cpp](src/main.cpp) 的 SHA-256 为 `17ccebfe8cf707aeb373a45f4e17faab6c995eb62c4bde05176add7eefaa863b`，与此次提供的最新生产源码哈希一致。这个对应关系只说明源码一致；本次没有烧录、串口访问、MQTT 发布或实物红外测试，也不说明最新 UNO 源码已烧录。

[platformio.ini](platformio.ini) 固定 `platformio/espressif32@6.9.0`、`esp32-c3-devkitm-1`、已安装的 Arduino 框架包 `3.20017.241212+sha.dcc1105b`（Arduino ESP32 **2.0.17**）、IRremoteESP8266 `2.9.0` 和 PubSubClient `2.8.0`；native 为 `1.2.1`，Unity 为 `2.6.1`。私有配置的 IR 库约束曾是 `^2.8.6`，实际安装版本为 `2.9.0`，这里按实际元数据固定。源码访问 `_IRrecv::params` 等库内部状态，因此不应随意换库版本。这些固定项不是全部传递工具依赖的锁文件。

## 当前源码行为与限制

- node02 通过 TLS 8883 接入 MQTT，订阅命令，发布状态和事件；发布 QoS 0，LWT QoS 1。GPIO3 发射，GPIO4 接收，接线、电平和发射驱动须按实际硬件核对。
- `ac_preview` 验证允许的协议与状态，重置 `ac.next` 后返回事件，**不调用 `sendAc()`，不因该命令发射红外**。`ac_send` 只选择一个协议并调用一次 `sendAc()`；库自身可能按协议发送多个帧或重复帧，不把“一次函数调用”解释为单个物理帧。
- 仅保留原有协议允许列表、16–30°C 范围、模式与风速检查。`ac_send` 没有新增本地 disarm 开关；固件原本就能执行通过检查的命令。不能把正式目录整理理解为默认关闭控制或 HA 安全控制链已经验收。
- **启动本身也可能发射红外。** `setup()` 调用 `irsend.calibrate(38000)` 校准发射时序，该库的校准会输出载波；首次 MQTT 连接后约 800 ms 还会自动发送一次 NEC `0x5A02A55A`、32 bit 回环自检。这是既有非 AC 自检，不是 AC 控制帧，但仍是真实发射。`ir_loopback_test` 命令和串口 `SET_LOOPBACK` 也会触发 NEC 发射。
- 命令解析沿用简化的 `strstr`/`strtol` 和布尔前缀检查，不能宣称完整严格 JSON 校验或拒绝所有未知字段。`ttl_seconds` 只检查 1–30 范围，不计算消息实际年龄；去重仅保留 RAM 中最近 8 个 ID，重启即丢失。与[MQTT 契约](../../docs/mqtt-protocol.md)的严格校验/过期拒绝要求仍有差距；本次保持原行为，未扩大控制权限或允许列表。

## 首次构建与离线测试

安装 PlatformIO Core、Python 3 和本机 C++ 编译器后，从仓库根目录执行。首次解析依赖需要下载固定的平台和库；下列步骤没有烧录或串口命令。

```bash
cd firmware/esp32-c3-ir
pio test -e native
# 安装该构建环境的依赖，供 AC handler 离线测试使用，不连接设备：
pio pkg install -e esp32c3
python3 -B test/test_ac_handler.py
cp -n include/secrets.example.h include/secrets.h
# 在本机编辑 include/secrets.h，替换全部占位值后再构建：
pio run -e esp32c3
```

凭据只写入已忽略的 `include/secrets.h`，模板是 [secrets.example.h](include/secrets.example.h)。必须填写 `WIFI_SSID`、`WIFI_PASSWORD`、`MQTT_HOST`、`MQTT_USERNAME`、`MQTT_PASSWORD` 和受信 Broker CA PEM `MQTT_CA`；主机须与证书匹配。`.invalid` 主机和 CA 占位内容不能用于连接。源码直接包含 `secrets.h`，不会自动退回模板；两种离线测试均不需要凭据。

[test_ir_logic](test/test_ir_logic/test_main.cpp) 检查 AC 状态范围、去重/TTL 范围和 NEC 匹配。[test_ac_handler.py](test/test_ac_handler.py) 提取正式源码中的实际 handler，使用 IRremoteESP8266 的主机测试后端检查 preview 零发送、单次 `sendAc()`、状态重置、Kelvinator 编解码、GREE 关机及拒绝路径。它只编译 Kelvinator/GREE/NEC 子集，不能代表完整允许列表或实物空调兼容性；测试中的 MIDEA 被刻意禁用，用于检查“不支持”拒绝路径。

已有 IRremoteESP8266 `2.9.0` 的本地源码时，可用 `IRREMOTEESP8266_DIR=/path/to/IRremoteESP8266 python3 -B test/test_ac_handler.py` 只读复用，避免下载或复制库。native 与 handler 测试都没有 GPIO、串口、Broker 或真实发射，不能据此宣称硬件重新验收通过。

2026-11-05 正式目录验证：`pio test -e native` 3/3、实际 handler 的主机测试 1/1 通过，`pio run -e esp32c3` 构建通过。构建临时使用模板假配置，结束后已删除；占用 Flash 1,154,408 B、RAM 40,956 B。没有执行 upload、串口连接、MQTT 发布或实物发射；编译产物不等于当前板上二进制。
