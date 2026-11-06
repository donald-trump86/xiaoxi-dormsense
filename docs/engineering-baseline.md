# 工程基线与模块验证总览

本文汇总 **XiaoXi DormSense** 各功能模块的正式源码路径、构建方式与自动化测试覆盖情况，作为代码审查、环境复现与课程验收的全局参考表。

---

## 1. 模块源码与产物对照表

| 模块分层 | 仓库目录 | 核心实现内容 | 关键配置 / 锁文件 |
| --- | --- | --- | --- |
| 感知陪伴固件（`node01`） | [firmware/arduino-uno-r4/](../firmware/arduino-uno-r4/README.md) | SHT31 串口分帧、LM393 光照采样、A0/点阵寄存器锁解耦、12×8 LED 点阵五幕陪伴动效、三线按钮手势 | [platformio.ini](../firmware/arduino-uno-r4/platformio.ini)（`renesas-ra@1.9.0`） |
| 红外学习固件（`node02`） | [firmware/esp32-c3-ir/](../firmware/esp32-c3-ir/README.md) | 被动静默启动、`learn1` 300 项原始微秒脉冲采集、14 字段空调状态解码、发射暂停接收中断、一次性挑战码回放 | [platformio.ini](../firmware/esp32-c3-ir/platformio.ini)（`espressif32@6.9.0`、`IRremoteESP8266@2.9.0`、`ArduinoJson@7.2.1`） |
| 安全桥接服务 | [services/bridge/](../services/bridge/README.md) | `validator.py`（契约与防重放）、`read_gateway.py`（五实体只读网关）、`inference_egress.py`（HTTPS 域名白名单代理）、`dashboard_ingress.py`（9119 入口转发） | [Dockerfile](../deploy/images/runtime/Dockerfile)、[source-sha256.json](../services/bridge/source-sha256.json) |
| 红外学习与回放服务 | [services/ir_learning/](../services/ir_learning/README.md) | 45 秒按键采样会话、14 字段前后比对、未知协议人工标签归档、两阶段单次回放 CLI | [compose.ir-learning.yaml](../deploy/compose.ir-learning.yaml) |
| Home Assistant 配置 | [home-assistant/](../home-assistant/README.md) | 温度、湿度、光照、按钮事件、红外事件五大实体定义，35 秒过期机制与 24 小时滚动历史保留自动化 | [node01.yaml](../home-assistant/mqtt/real/node01.yaml)、[environment-retention.yaml](../home-assistant/automations/environment-retention.yaml) |
| 历史统计与卡尔曼滤波 | [analytics/](../analytics/README.md) | 24 小时滑动窗口有效样本清洗、断流检测、一维随机游走因果卡尔曼滤波平滑估计与 SQLite 只读报表 CLI | [environment.py](../analytics/src/environment.py)、[recorder_report.py](../analytics/src/recorder_report.py) |
| Hermes 智能体定制 | [hermes/](../hermes/README.md) | 本地 Faster-Whisper 转写、Edge TTS 小西声线、日常单会话延续、原生红外学习插件、终端 `xiaoxi` 皮肤与全套交小西品牌图标 | [manifest.json](../hermes/patches/manifest.json)、[requirements-voice.lock](../hermes/requirements-voice.lock) |

---

## 2. 自动化测试套件汇总

| 测试套件 | 测试数量 | 执行命令 | 覆盖重点 |
| --- | --- | --- | --- |
| 仓库静态检查 | 40 MD / 11 JSON / 16 YAML | `python scripts/check_repository.py` | 本地文档链接存在性、JSON Schema 严格校验、YAML 语法与 `!include` 解析 |
| 根集成测试 | 31 项 | `python -m unittest discover -s tests -p 'test_*.py' -v` | 遥测契约正反例、模拟器输出、八容器网络隔离、HA 24h 保留配置 |
| 桥接服务测试 | 190 项 | `python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v` | 验证器握手超时与单调水位、只读网关路径白名单与 HTTP 边界、出口代理域名过滤 |
| 卡尔曼滤波测试 | 23 项 | `python -m unittest discover -s analytics/tests -p 'test_*.py' -v` | 一维卡尔曼滤波收敛性、35s 断流与重启重置、夏令时 86,400 秒窗口边界、只读 SQLite 快照 |
| 红外学习服务测试 | 52 项 | `python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v` | 脉冲分包重组、14 字段前后比对、防错按重采、挑战码单次回放与防重放日志 |
| Hermes 插件测试 | 14 项 | `python -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v` | 空调初始化/学键/状态工具参数校验与固定六动作白名单 |
| UNO R4 固件测试 | 34 项 | `pio test -d firmware/arduino-uno-r4 -e native` | SHT31 串口断帧拼接、EEPROM 启动计数、光敏归一化、点阵字模与三线按钮手势 |
| ESP32-C3 固件测试 | 13 项 native + 22 项主机测试 | `pio test -d firmware/esp32-c3-ir -e native` 及 `python -m unittest discover -s firmware/esp32-c3-ir/test -p 'test_*.py' -v` | `learn1` 命令校验、脉冲时序格式化、NEC 离线分析器与 `IRremoteESP8266` 真实编解码协同 |
| Hermes 离线补丁测试 | 26 项 Python + 18 项前端 | `python hermes/tests/run_offline.py` | 16 文件补丁精确重建、语音合成/转写边界、语音播放回调与日常单会话延续逻辑 |

---

## 3. 容器与固件可复现构建命令

```bash
# 编译 UNO R4 WiFi 与 ESP32-C3 固件（仅编译验证，无需插入开发板）
pio run -d firmware/arduino-uno-r4 -e uno_r4_wifi
pio run -d firmware/esp32-c3-ir -e esp32c3

# 构建桥接服务与 Hermes 本地镜像
docker build -f deploy/images/runtime/Dockerfile -t xiaoxi-dormsense/runtime:local .
docker build -f hermes/Dockerfile -t xiaoxi-dormsense/hermes:local hermes
```
