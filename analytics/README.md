# 数据分析（Planned）

负责人 D。初始化仅提供输入契约、依赖候选与目录说明，**没有已实现的采集器、数据库、异常检测或日报服务**。

## 约定的输入与存储

通过 Broker 账号只读订阅 `xiaoxi/dorm/+/telemetry`（需要时读 status/event），符合[协议](../docs/mqtt-protocol.md)。校验 JSON Schema 与字段语义，再存 `{received_at, topic, payload}` 包络，原始 timestamp/null 不可覆盖。唯一键 `(node_id, boot_id, sequence)`，simulated 与实测数据隔离。

首期使用本机 JSONL 原始追加存储、Pandas 分析，按实际需求再引入 SQLite/InfluxDB；暂不部署 Grafana 或训练模型。原始记录放 `data/raw/`（忽略），输出放 `data/processed/`（忽略），只有无隐私的模拟样例可入 Git。

计划管线：采集与坏消息隔离 → 去重/清洗 → 时序聚合与缺失统计 → 描述统计/相关性 → 阈值与滑动窗口异常 → 图表和日报。缺失值不能默认填 0；保留插值标记、规则版本与时间窗，不能把插值当实测。实时告警不依赖 LLM。

## 开发准备

先使用根目录开发虚拟环境；分析开始时按需安装：

```bash
python -m pip install -r analytics/requirements.txt
```

这是兼容范围候选，不是经过完整分析流程验收的锁文件。`src/` 用于可测试逻辑，`notebooks/` 用于探索，不将正式管线锁在 Notebook 内。后续采集器如用 Paho，需在本模块声明其依赖而非借用全局环境。

D/E 共同确定脱敏历史报告接口：至少包含窗口、时区、节点、有效样本数、缺失率、simulated、规则版本、统计值和事件列表。接口尚未实现，不声称 Hermes 已能读本地报告。实验方法见[课程实验](../docs/experiments.md)。
