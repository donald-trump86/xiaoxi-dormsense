# Home Assistant 配置与证据边界

现有实例已经接收真实温湿度、相对光照、按钮和红外事件，并有 Hermes 经固定实体网关查询的记录。本目录同时保留历史 node90 示例与真实节点模板。2026-11-05 按用户选择，为三类环境历史应用一天保留策略，经过 HA 原生配置检查和定向重载；其他实体配置保留。

| 文件 | 范围 |
| --- | --- |
| [configuration.example.yaml](configuration.example.yaml) / [mqtt/sensors.yaml](mqtt/sensors.yaml) | 保留的 node90 模拟开发入口；原样例字节未改动，不代表真实 node01 |
| [configuration.secure.example.yaml](configuration.secure.example.yaml) | 新实例入口，使用 `!include_dir_merge_list mqtt/real` |
| [mqtt/real/node01.yaml](mqtt/real/node01.yaml) | 真实三路周期实体，消费 validated topics，约 35 秒过期 |
| [mqtt/real/events.yaml](mqtt/real/events.yaml) | 按钮和红外最近事件；各自有可用性状态，不是周期温湿度或空调反馈 |
| [automations/environment-retention.yaml](automations/environment-retention.yaml) | 每 5 分钟及 HA 启动时，仅 purge 三类环境实体的一天前状态 |
| [dashboards/dorm.example.yaml](dashboards/dorm.example.yaml) | 历史手工面板示例，需核实实际 entity ID，不是五实体自动配置 |

五个固定实体的完整 ID 见[网关模板](../deploy/examples/gateway.example.json)，分别对应温度、湿度、相对光照、红外事件和按钮事件。名称冲突会影响实际 ID，必须在 UI 核对，不据模板文本宣称已创建成功。

周期通道在 validator 执行完整契约校验，HA 再检查对应元数据和状态；缺测映射为未知，不能用旧数补齐。光照是归一化相对比例，没有 lux 单位。HA 的 `received_at` 为接收时间，`last_changed` 不等于最新采样时刻；node01 35 秒时效不机械套在事件驱动实体上。

事件模板只做有限结构检查，不替代完整事件接入校验。节点离线时 HA 可能保留旧属性，正式网关会在不可用状态清空事件内容。最近一次红外接收、发送成功回执和实际空调状态必须区分。

MQTT 集成通过用户 UI 私下配置，正式模板使用只读 `xiaoxi_ha_read`，不把口令写进仓库。HA 后端 Token 仅供网关，Hermes 拿独立查询凭据；原生 HA Token 不天然只读。本目录没有继电器、设备控制自动化或预测实体。

三路环境实体已去掉 `state_class: measurement`，以停止额外的长期统计；现有实例也已通过原生接口一次性清除这三项的旧短期/长期统计。普通 `recorder.purge_entities` 不会代做这一步。最近一天原始状态仍供只读统计与平滑估计；其他设备历史不参与这次清理。查询严格截取 24 小时，物理清理可能滞后 5 分钟加队列时间。保留策略、估计与尚未提供的 Hermes 历史接口见[历史说明](../docs/history-and-kalman.md)。新实例操作按[部署指南](../docs/deployment.md)，不覆盖已有 HA 配置。静态 YAML/Jinja 字符串测试不能替代实际 HA 加载、实体值、LWT 和过期验收。
