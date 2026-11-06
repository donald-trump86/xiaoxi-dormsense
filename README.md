# 交小西宿舍智能体 · XiaoXi DormSense

**交小西（XiaoXi DormSense）** 是面向高校宿舍微环境感知与自然语言交互的物联网与智能体课程工程项目，涵盖**无线传感网络、物联网安全通信、流式数据滤波分析与大语言模型智能体（Hermes Agent）**。

系统通过两块微控制器节点采集宿舍真实温湿度、相对光照、物理按钮手势与空调红外信号，经双向校验的 MQTT over TLS（8883）总线汇入常驻契约验证器与 Home Assistant，再通过五实体只读安全网关和红外学习服务接入定制的 Hermes 语音/文本智能体（`xiaoxi`），实现**环境状态查询、LED 点阵情绪陪伴、一维因果卡尔曼滤波分析与学习型空调遥控**。

---

## 系统架构与数据流

```text
[感知陪伴节点 node01: Arduino UNO R4 WiFi]
  ├─ SHT31 串口温湿度 (D0/Serial1, 9600 8N1)
  ├─ LM393 光敏电阻 (A0, 0~1 归一化光照)
  ├─ 三线按钮手势 (D2/D3/D4: 单击/双击/长按)
  └─ 12×8 板载 LED 点阵 (五幕状态与陪伴动画)
          │
          │  MQTT over TLS 8883 (CA 校验 + 独立账号 ACL)
          ▼
[Mosquitto Broker] ──► [node01-validator 契约与防重放验证]
          │                        │
          │                        ▼ (xiaoxi/validated/node01/#)
          ▼                [Home Assistant 核心平台]
[红外学习节点 node02: ESP32-C3]      ├─ 五大实体状态与 35s 断流过期
  ├─ 38kHz 红外接收头 (GPIO4)        ├─ 每 5 分钟自动清理 24h 前历史状态
  └─ 940nm 红外发射头 (GPIO3)        └─ SQLite 只读一维因果卡尔曼滤波 (analytics/)
          │                        │
          ▼                        ▼
[ir-learning 红外学习与回放服务]  [read-gateway 五实体只读安全网关]
          │                        │
          └──────────┬─────────────┘
                     ▼ (internal agent 隔离网段)
        [Hermes Agent · 交小西语音与日常会话界面 (9119)]
          ├─ DeepSeek 对话推理 (经 inference-egress 域名白名单代理)
          ├─ Faster-Whisper 本地语音转写 + Edge TTS 云端语音合成
          └─ 网页日常单会话延续 + 终端/网页全套交小西品牌界面
```

---

## 核心工程特性

1. **双板协同与边缘交互**
   - **感知陪伴节点（`node01`，Arduino UNO R4 WiFi）**：解析 SHT31 串口帧并采样 LM393 光照，解决 RA4M1 芯片 A0 ADC 与板载 12×8 LED 点阵的寄存器锁冲突；点阵屏以 6 秒/幕无闪烁轮播笑脸、温湿度、光照与暗光睡眠 `Zzz` 动画，并支持三线按钮单击切换、双击查询、长按开始录音、松开结束并发送的语音手势。
   - **红外学习节点（`node02`，ESP32-C3）**：支持原装格力空调遥控器 280 边沿双段长帧的原始微秒脉冲采集（`learn1` 协议最高 300 项）、14 字段标准状态比对与一次性挑战码（Challenge-Commit）安全回放；两块开发板可通过 `5V/GND` 单 USB 线串联供电。
2. **零信任网络隔离与最小权限边界**
   - 容器层划分为后端设备网段（`backend`）与智能体内部网段（`agent: internal`）。
   - `read-gateway` 将 Home Assistant 高权限 Token 封存在网关侧，仅向智能体暴露 5 个固定实体的 `GET` 接口（温度、湿度、光照、按钮事件、红外事件），物理阻断越权写操作。
   - `inference-egress` 代理仅放行推理、语音合成、城市定位与天气查询所需的 7 个固定 HTTPS 域名。
3. **24 小时滚动数据治理与一维因果卡尔曼滤波**
   - Home Assistant 自动化每 5 分钟清理 24 小时前的环境历史状态，控制数据库体积。
   - `analytics/` 模块直接以只读方式分析 SQLite 历史库，在严格校验元数据与 35 秒断流重初始化的基础上，对温湿度与光照执行一维随机游走因果卡尔曼滤波平滑估计。
4. **交小西自然语言、语音与日常记忆**
   - 基于固定摘要的上游 Hermes 镜像，通过可复现的 17 文件精确补丁（`hermes/patches/hermes.patch`）集成 Faster-Whisper 本地语音识别、Edge TTS 小西声线播报、网页日常单会话自动延续、红外学习与单次发射原生插件（`xiaoxi_ir_learning`）、动态城市天气实况插件（`xiaoxi_weather`）及全套交小西品牌 UI。中文朗读保留负数与范围，实体按钮松开后自动结束收音并转写发送。

---

## 仓库目录导览

| 目录 / 文件 | 模块定位与学习入口 |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | 全系统分层架构、容器网络拓扑与安全边界设计 |
| [docs/hardware.md](docs/hardware.md) | UNO R4 WiFi 与 ESP32-C3 硬件清单、引脚接线表与供电方式 |
| [docs/mqtt-protocol.md](docs/mqtt-protocol.md) | MQTT v1 Topic 树、遥测/事件/命令 JSON 契约与 `learn1` 红外学习协议 |
| [docs/ac-onboarding.md](docs/ac-onboarding.md) | 空调红外协议排障历程、280 边沿长帧学习原理与交互式逐键录制流程 |
| [docs/history-and-kalman.md](docs/history-and-kalman.md) | HA 24h 滚动保留策略、一维因果卡尔曼滤波数学模型与 CLI 用法 |
| [docs/hermes-daily-use.md](docs/hermes-daily-use.md) | 交小西网页端日常单会话、语音交互、记忆机制与空调按键学习指南 |
| [docs/deployment.md](docs/deployment.md) | 开发栈与八容器安全栈部署步骤、TLS 证书生成与配置说明 |
| [docs/development.md](docs/development.md) | 本地开发环境搭建、模块扩展方法与代码提交流程 |
| [docs/experiments.md](docs/experiments.md) | 五大核心课程实验设计（端到端感知、断线恢复、滤波清洗、安全隔离、红外学习） |
| [docs/commit-guide.md](docs/commit-guide.md) | 按功能拆分的细粒度 Git 提交学习索引，适合按提交顺序研读代码演进 |
| [firmware/](firmware/README.md) | 正式固件统一入口、本地配置边界与离线验证命令 |
| [firmware/arduino-uno-r4/](firmware/arduino-uno-r4/README.md) | `node01` 感知与 LED 点阵陪伴固件及 39 项 PlatformIO native 单元测试 |
| [firmware/esp32-c3-ir/](firmware/esp32-c3-ir/README.md) | `node02` 红外学习/回放固件、脉冲时序分析器与主机/native 测试套件 |
| [services/bridge/](services/bridge/README.md) | 常驻验证器、五实体只读网关、HTTPS 出口白名单代理与 9119 入口转发服务 |
| [services/ir_learning/](services/ir_learning/README.md) | 遥控器逐键学习、完整状态样本目录与 HTTP / CLI 共用的挑战码单次发射 |
| [analytics/](analytics/README.md) | 24h 环境历史统计、一维因果卡尔曼滤波器与 HA SQLite 只读报表工具 |
| [hermes/](hermes/README.md) | Hermes 镜像构建配方、17 文件源码补丁、红外学习插件、语音锁文件与品牌模板 |
| [home-assistant/](home-assistant/README.md) | Home Assistant 真实节点配置、事件实体模板与 24h 滚动保留自动化 |
| [deploy/](deploy/README.md) | Docker Compose 编排文件、运行时镜像 Dockerfile 与配置模板 |
| [simulator/](simulator/README.md) | 无需硬件即可生成合规遥测流的 Python 离线/本地模拟器（`node90`） |
| [tests/](tests/README.md) / [scripts/check_repository.py](scripts/check_repository.py) | 跨模块自动化测试套件与仓库链接/Schema/YAML 静态检查工具 |

---

## 快速开始与本地验证

克隆仓库后，无需连接真实开发板或启动 Docker 容器，即可在本地 Python 虚拟环境中运行全套单元测试与静态检查，快速熟悉协议与各模块逻辑：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt -r services/bridge/requirements.txt

# 1. 运行仓库静态检查（Markdown 链接、JSON Schema、YAML 语法）
python scripts/check_repository.py

# 2. 运行根目录、安全桥接、卡尔曼滤波、红外学习与插件单元测试
python -m unittest discover -s tests -p 'test_*.py' -v
python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v
python -m unittest discover -s analytics/tests -p 'test_*.py' -v
python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v
python -m unittest discover -s hermes/tests -p 'test_*plugin.py' -v

# 3. 预览离线模拟遥测消息
python simulator/mqtt_node.py --count 3
```

如需构建开发板固件、启动容器服务或按步骤学习代码实现，请依次参阅 [本地初始化指南](docs/initialization.md)、[部署指南](docs/deployment.md) 与 [Git 提交学习索引](docs/commit-guide.md)。
