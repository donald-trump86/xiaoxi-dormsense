# Home Assistant 实体与保留策略配置（`home-assistant`）

本目录存放 Home Assistant 的配置文件模板、MQTT 传感器定义与 24 小时滚动历史保留自动化规则。

---

## 1. 配置文件结构

| 文件路径 | 功能说明 |
| --- | --- |
| [configuration.example.yaml](configuration.example.yaml) | 轻量开发联调栈配置模板 |
| [configuration.secure.example.yaml](configuration.secure.example.yaml) | 安全隔离栈配置模板（通过 `!include` 加载真实节点传感器、事件传感器与保留自动化） |
| [mqtt/real/node01.yaml](mqtt/real/node01.yaml) | `node01` 真实温湿度与光照传感器定义（订阅 `xiaoxi/validated/node01/telemetry`，设置 `expire_after: 35` 秒自动过期，省略 `state_class` 以免生成永久统计汇总） |
| [mqtt/real/events.yaml](mqtt/real/events.yaml) | `node01` 物理按钮事件（`sensor.xiaoxi_node01_button_event`）与 `node02` 红外事件（`sensor.xiaoxi_node02_ir_event`）实体定义 |
| [mqtt/sensors.yaml](mqtt/sensors.yaml) | 本地模拟器（`node90`）与演示实体模板 |
| [automations/environment-retention.yaml](automations/environment-retention.yaml) | 启动时及每 5 分钟执行一次 `recorder.purge_entities`（`keep_days: 1`），自动清理温度、湿度、光照 24 小时前的历史状态 |
| [dashboards/dorm.example.yaml](dashboards/dorm.example.yaml) | 宿舍环境监控 Lovelace 仪表盘示例 |
