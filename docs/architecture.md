# 系统架构设计

本文介绍 **XiaoXi DormSense（交小西宿舍智能体）** 的分层架构、容器网络拓扑、核心组件职责及设计取舍，帮助后续学习者快速建立全局视图。

---

## 1. 架构设计目标

在高校宿舍场景中构建物联网与大模型结合的系统，面临三个核心工程问题：

1. **边缘端与主机端的算力分工**：微控制器擅长确定性的定时采样、协议解析与实时硬件驱动，但不适合直接运行复杂统计或大模型推理；主机端适合做流式校验、历史清洗、卡尔曼滤波与自然语言交互。
2. **大模型接入后的安全边界**：Home Assistant 原生的长效 Token 默认具备调取任意服务（写操作）的权限。如果直接把高权限 Token 和内网权限交给大模型容器，提示词注入或模型幻觉可能误触设备。
3. **红外家电控制的协议兼容性**：商用空调遥控器常采用双段长帧（如格力 280 边沿帧），开源红外库的固定合成函数未必匹配具体机型。采用“原装遥控器原始波形采集 + 标准库状态防呆比对 + 单次挑战码回放”能够兼顾通用性与安全性。

围绕以上三点，系统划分为**边缘硬件层、加密传输与契约层、平台与滤波分析层、隔离智能体层**四个部分。

---

## 2. 端到端分层拓扑

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. 边缘硬件层 (5V/GND 单口串联供电)                                        │
│                                                                            │
│  [node01: Arduino UNO R4 WiFi]            [node02: ESP32-C3 红外节点]      │
│   • SHT31 串口温湿度 (D0/Serial1)          • 38kHz 红外接收头 (GPIO4)      │
│   • LM393 光敏模块 (A0, 0~1 相对光照)      • 940nm 红外发射管 (GPIO3)      │
│   • 三线物理按钮 (D2/D3/D4 单/双/长按)     • learn1 300项原始脉冲采集      │
│   • 12×8 LED 点阵五幕陪伴动效              • 14字段状态解码与挑战码回放    │
└───────────────────┬───────────────────────────────────────┬────────────────┘
                    │ MQTT over TLS 8883 (双向校验 + ACL)   │
                    ▼                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 2. 后端设备网段 (Docker network: backend)                                  │
│                                                                            │
│  [mosquitto] ──(raw node01)──► [node01-validator]                          │
│       │                         • JSON Schema 校验 + 跨字段一致性          │
│       │                         • (boot_id, sequence) 持久化防重放         │
│       │                                   │                                │
│       │ (node01/02 events)                ▼ (xiaoxi/validated/node01/#)    │
│       └──────────────────────► [home-assistant]                            │
│       │                         • 5 个核心实体 + 35s 断流自动过期          │
│       │                         • 每 5 分钟自动清理 24h 前环境历史状态     │
│       │                         • SQLite 供 analytics/ 卡尔曼滤波只读分析  │
│       ▼                                   │                                │
│  [ir-learning]                            ▼                                │
│   • 逐键学习会话与前后状态比对      [read-gateway]                         │
│   • 私有 0700 波形存储与挑战码回放   • 仅暴露 5 个允许实体的只读 GET       │
└───────────────────┬───────────────────────┬────────────────────────────────┘
                    │ HTTP 8090             │ HTTP 8080 (剥离后端 Token)
                    ▼                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 3. 智能体内部网段 (Docker network: agent, internal: true)                  │
│                                                                            │
│  [hermes (交小西智能体)]                                                   │
│   • 原生工具：ha_get_state / ha_list_entities + xiaoxi_ir_learning 插件    │
│   • 本地语音识别：Faster-Whisper (base) + 简体中文规范化 (zhconv)          │
│   • 网页日常单会话自动延续 + 终端/网页交小西品牌界面                       │
└─────────┬─────────────────────────────────────────────────┬────────────────┘
          │ HTTP CONNECT 3128                               │ HTTP 9119
          ▼                                                 ▼
┌─────────────────────────────────────┐   ┌──────────────────────────────────┐
│ [inference-egress] (egress-outbound)│   │ [dashboard-ingress] (宿主机 9119)│
│  • 仅放行 DeepSeek / Edge TTS 等    │   │  • 将宿主机 127.0.0.1:9119 转发  │
│    7 个固定 HTTPS 域名:443          │   │    至内部网段的 hermes:9119      │
└─────────────────────────────────────┘   └──────────────────────────────────┘
```

---

## 3. 八容器安全编排与职责表

在完整安全部署（[deploy/compose.secure.yaml](../deploy/compose.secure.yaml) 与 [deploy/compose.ir-learning.yaml](../deploy/compose.ir-learning.yaml)）中，系统由 8 个容器协同运行：

| 容器服务名 | 所属网络 | 运行身份与文件系统 | 核心职责 |
| --- | --- | --- | --- |
| `mosquitto` | `backend` | `1883:1883` | 提供 8883 TLS 加密接入与 1883 内网监听，通过独立账号与 [ACL 规则](../deploy/examples/mosquitto-acl.conf) 隔离各节点读写主题 |
| `node01-validator` | `backend` | `10001:10001`（只读根文件系统，`cap_drop: ALL`） | 订阅 `node01` 原始遥测，执行 JSON Schema 校验与 `(boot_id, sequence)` 单调水位检查，合格消息重发布至 `xiaoxi/validated/node01/#` |
| `home-assistant` | `backend` | 官方镜像默认 | 汇聚 5 个核心传感器实体，维护 35 秒断流过期机制与 24 小时滚动历史保留自动化 |
| `read-gateway` | `backend` + `agent` | `10001:10001`（只读根文件系统，`cap_drop: ALL`） | 持有 HA 后端 Token，向 `agent` 网段仅暴露 5 个白名单实体的只读 `GET /api/states` 接口，拒绝一切 `POST` 服务调用 |
| `ir-learning` | `backend` + `agent` | `10001:10001`（只读根文件系统，独立 `/state` 卷） | 连接 `node02` 与 Hermes 红外插件，管理 45 秒采样、14 字段比对与私有样本目录，通过 HTTP / CLI 共用挑战码单次发射 |
| `hermes` | `agent`（`internal: true`） | 容器内部服务 + `/opt/data` 持久卷 | 运行交小西对话引擎、Faster-Whisper 语音转写、Edge TTS 语音合成与 9119 Web UI，无直接外网路由 |
| `inference-egress` | `agent` + `egress-outbound` | `10001:10001`（只读根文件系统，`cap_drop: ALL`） | 为 `hermes` 提供 HTTP `CONNECT` 代理，仅放行推理、语音合成、城市定位与天气查询所需的 7 个固定 HTTPS 域名 |
| `dashboard-ingress` | `agent` + `dashboard-ingress` | `10001:10001`（只读根文件系统，`cap_drop: ALL`） | 由于 Docker `internal` 网络不直接映射宿主机端口，负责将宿主机 `9119` 安全转发至 `hermes:9119` |

---

## 4. 关键工程设计解析

### 4.1 为什么要设立独立 `node01-validator`？
微控制器受限于内存与算力，直接接入 Home Assistant 时若出现残缺帧、异常浮点数或网络重传乱序，容易污染历史曲线。`validator.py` 在进入 HA 之前完成严格 JSON Schema 校验，并将每个 `boot_id` 的最高 `sequence` 持久化到 `/var/lib/xiaoxi`，确保只有结构合规、序号严格递增的真实样本进入平台。

### 4.2 为什么要把 `read-gateway` 放在 HA 与 Hermes 之间？
Home Assistant 的 Long-Lived Access Token 不支持“仅允许读取某几个实体、禁止调用任何服务”的细粒度权限。通过独立的 `read_gateway.py`：
- 即使 `hermes` 调用了全量列表工具 `ha_list_entities`（请求 `/api/states`），网关也只会在后端逐一读取配置的 5 个固定实体并裁剪敏感属性后返回，不会拉取 HA 全量实体。
- 任何针对 `/api/services/*` 的写请求在网关层直接返回 `405 Method Not Allowed`。

### 4.3 历史数据治理与一维因果卡尔曼滤波
为避免高频采样（10 秒/帧）导致 SQLite 数据库无限膨胀，系统结合了两层设计：
1. **HA 24 小时滚动清理**：[environment-retention.yaml](../home-assistant/automations/environment-retention.yaml) 每 5 分钟自动清理 3 个环境实体超过 24 小时的原始状态。
2. **一维因果卡尔曼滤波（[analytics/](../analytics/README.md)）**：针对温湿度与光照的微幅量化抖动，采用标量随机游走状态空间模型，根据相邻样本的真实时间步长 $\Delta t$ 动态更新预测协方差 $P^- = P + q\Delta t$，并在断流超过 35 秒或节点重启（`boot_id` 变化）时自动重置滤波器状态，输出平滑的当前估计值。
