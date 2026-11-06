# 无线传感节点模拟器（`simulator`）

本目录提供无需连接物理开发板即可生成合规 MQTT v1 遥测流的 Python 模拟器 [mqtt_node.py](mqtt_node.py)，方便在纯软件环境下验证消息契约、Mosquitto Broker 与 Home Assistant 实体配置。

---

## 1. 功能特点

- 生成严格符合 [schemas/telemetry.schema.json](../schemas/telemetry.schema.json) 的 JSON 消息，自动标记 `"simulated": true` 并默认使用测试节点编号 `node90`（与实机 `node01` 隔离）。
- 支持注入缺测状态（`--missing-light` 等）以测试下游对 `null` 值的处理逻辑。
- 未指定 `--host` 时默认在终端打印 JSON（Dry-Run 模式）；指定 `--host` 时通过 MQTT 协议发布至目标 Broker。

---

## 2. 常用命令

```bash
source .venv/bin/activate

# 1. 本地打印 3 条模拟遥测帧（无需启动 Broker）
python simulator/mqtt_node.py --count 3

# 2. 向本地 1883 Broker 连续发送 10 条遥测帧（间隔 2 秒）
python simulator/mqtt_node.py --host 127.0.0.1 --port 1883 --count 10 --interval 2

# 3. 模拟光照传感器缺测（light=null, sensor_status.light="missing"）
python simulator/mqtt_node.py --count 1 --missing-light
```
