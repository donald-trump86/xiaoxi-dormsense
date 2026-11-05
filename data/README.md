# 数据目录与当前存储

本目录有用途，应保留。2026-11-05 整理前只有三个跟踪文件、合计约 1.4 KB，没有可清理的大型原始数据目录：本说明、[合成协议样例](samples/telemetry.simulated.json)和[处理结果说明](processed/README.md)。样例被[仓库检查器](../scripts/check_repository.py)、[协议测试](../tests/mqtt/test_protocol.py)和[CI](../.github/workflows/ci.yml)使用；删除会破坏离线检查。

## 已有与预留

| 位置 | 用途与当前状态 |
| --- | --- |
| [samples/telemetry.simulated.json](samples/telemetry.simulated.json) | 人工构造、`simulated=true` 的契约样例，不是实测数据 |
| `raw/` | 为本地原始记录预留，运行时创建并被 Git 忽略；当前没有常驻采集器自动写入 |
| `processed/` | 预留本地统计、图表和分析输出，只有说明文件可提交 |
| HA 的 `/config/home-assistant_v2.db` | 现有部署确实保存状态历史，位于 HA 的运行存储，不在本目录；数据库不能直接入 Git |
| validator 的持久状态 | 防重放水位，不是传感器历史库 |

私有实验中还有有界串口/MQTT 抓取，用于追溯特定实验；它们不是连续历史采集服务，也不能自动拼成完整时间序列。数据存在于 HA 不代表 Hermes 已有历史查询权限，目前网关只读固定实体的当前状态。

## 后续采集约定

首个正式采集器尚未实现。计划优先只读订阅经过校验的 node01 遥测，追加保存接收时间、topic、原始 payload、代码版本和实验编号；原始 `timestamp=null` 不改写成伪造的设备测量时间。按 `(node_id, boot_id, sequence)` 去重，模拟、真实、回放和插值分开标记，保留原始记录并将坏消息隔离。

宿舍数据可能反映在室时间和生活规律，默认本机保存、最小采集、有限保留，公开前经人工脱敏审查。不要把整个 HA 数据库或未经同意的原始记录上传模型。Git 忽略不等于自动脱敏。

历史、滤波与预测的实际边界及下一步方案见[历史数据与卡尔曼滤波](../docs/history-and-kalman.md)；实验元信息见[实验方案](../docs/experiments.md)。