# MQTT 通信协议 v1

状态：**v1.0 初始契约，待 A/B/C/D 联合评审后冻结**。修改须经 PR、兼容性说明并同步 Schema、示例、固件、HA 与测试。优先单宿舍多节点，不做动态服务发现或复杂 RPC。

## 1. 命名与边界

前缀 `xiaoxi/dorm`，节点 ID 匹配 `node[0-9]{2,3}`（如 `node01`），由 A 分配且不得重复。宿舍地址、姓名、学号不能成为 ID。MQTT 客户端 ID 也必须唯一，例如 `xiaoxi-node01`；模拟器默认用 `node90`，避免冒充真实设备。

| Topic | 发布方 → 订阅方 | QoS（发布 / 订阅） | Retain |
| --- | --- | --- | --- |
| `xiaoxi/dorm/<node_id>/telemetry` | 节点 → HA、分析只读采集器 | 0 / 1（实际不高于 0） | 否 |
| `xiaoxi/dorm/<node_id>/status` | 节点/LWT → HA、分析 | 1 / 1；库受限时发布 0 | 是 |
| `xiaoxi/dorm/<node_id>/event` | 节点 → 确定性事件处理器 | 1 / 1；库受限时发布 0 | 否 |
| `xiaoxi/dorm/<node_id>/command` | HA → 节点 | 1 / 1 | **否** |

遥测每 10 秒一次为初始建议，可配置。QoS 0 适合课程实时采样；接受丢失并用序列号评估，不声称可靠存储。QoS 1 可能重复，不等于恰好一次。固件选 MQTT 库前验证 UNO R4 支持与 QoS 能力（某些库仅支持 QoS 0 发布），记录降级，不把它隐藏成 QoS 1。默认不自动补传历史数据。

MQTT 3.1.1 足够。报文 UTF-8 JSON，建议不超过 1024 字节；固件明确配置收发缓冲区并测量内存。合规接收端须拒绝无效 JSON、错误版本、Topic 与 payload 不一致的 node_id；记录原因，不让单条坏消息终止采集。此为实现验收要求，不代表现有 HA YAML 已具备完整 Schema 校验：当前配置仅限受信模拟源并有基础门卫，完整校验/坏消息隔离仍 Planned，真实接入前必须补齐。

## 2. 遥测契约

机器可验证契约：[telemetry.schema.json](../schemas/telemetry.schema.json)。有效模拟示例：[telemetry.simulated.json](../data/samples/telemetry.simulated.json)。

```json
{
  "schema_version": "1.0",
  "node_id": "node90",
  "boot_id": "sim-session-001",
  "timestamp": null,
  "sequence": 0,
  "simulated": true,
  "temperature": 24.5,
  "humidity": 55.0,
  "light": 0.5,
  "rssi": -60,
  "uptime": 0,
  "sensor_status": {"temperature": "ok", "humidity": "ok", "light": "ok"}
}
```

**该例完全为模拟数据，不是采集结果。** 所有七个业务字段（node_id、timestamp、sequence、temperature、humidity、light 及版本）以及 boot_id、simulated 必填。未知字段 v1 拒绝，以避免拼写错误被悄悄吞掉。

| 字段 | 类型 / 语义 |
| --- | --- |
| schema_version | 固定字符串 `1.0` |
| node_id | 必须与 Topic 的节点段相同 |
| boot_id | 每次进程/设备启动生成新 ID，1–64 位字母数字、`_` 或 `-`；固件实现需验证重启唯一性 |
| sequence | 非负整数，0 开始每产生一条样本加 1，不因断线而复位；同一次启动不复用；达到 2^32−1 前开启新 boot_id |
| timestamp | UTC RFC3339 `...Z` 字符串，或 `null`；**未同步时必须为 null** |
| simulated | 布尔；合成数据 true，真实采样 false，不允许用模拟值填装成真实值 |
| temperature | 摄氏度数值或 null；不设虚假的已确认传感器量程 |
| humidity | 相对湿度百分数 0–100 或 null |
| light | 0–1 归一化光照强度或 null，**不是 lux**；实际硬件确认后记录 ADC 标定方法 |
| rssi | 可选整数，dBm（−127 到 0） |
| uptime | 可选非负整数，自启动经过的秒数（固件处理 millis 溢出） |
| sensor_status | 可选对象，temperature/humidity/light 可分别取 ok、missing、error |

没有安装的传感器也保留字段，设为 null，可标记 missing。采集失败设 null/error，不能以 0 伪装缺失；禁止 NaN/Infinity。存在 sensor_status 时，ok 必须有数值，missing/error 必须为 null（接收侧另做语义检查）。单位变化属于协议变化。

## 3. 时间、重复与丢失

UNO 不假定存在准确 RTC 或完成 NTP。未同步时间为 null；仅已确认 UTC 同步时使用节点 timestamp。采集服务器到达时产生独立 `received_at`（UTC），原 payload 不变，存为 `{received_at, topic, payload}`。实时 HA 可直接消费传感器值，历史分析的默认时间轴用 received_at，另保留源时间和其质量。

唯一键 `(node_id, boot_id, sequence)` 用于去重；新 boot_id 切分运行段。按同一运行段序号缺口估计丢失，不能将设备重启误认为丢包。延迟统计见[实验方案](experiments.md)：没有时钟同步不能用 received_at − timestamp 声称单向网络延迟。

断线期间样本序列仍递增，恢复后发当前样本；v1 不提供持久离线缓存或历史补传。分析保留缺失标记，不伪造恢复的数据。高可靠缓存列为后续改进。

## 4. 在线状态与 LWT

在 CONNECT 时设置同一节点 status Topic 的 retained Last Will：

```json
{"schema_version":"1.0","node_id":"node90","state":"offline"}
```

连接成功发布 retained `{"schema_version":"1.0","node_id":"node90","state":"online"}`；主动退出先发布 offline，再 DISCONNECT。建议 keepalive 30 秒，实际离线检测时间依 Broker 和网络而定，应测量而非承诺瞬时。LWT 必须在连接前配置。

节点指数退避重连（建议 1、2、4…至 60 秒，增加少量抖动），成功后重订阅 command 并重新发 online。retained online 可能因 Broker 重启或非正常断网暂时陈旧，因此 HA 还需遥测超时（初值 35 秒）作为第二重不可用判断，不能把旧读数描述成当前正常。

retained status 中不放固定 boot 时间来假装真实离线时间；采集侧记到达时间。停用设备时由维护者清理 status retained 消息，不广泛清空 Broker。

## 5. 事件（接口预留，Planned）

```json
{"schema_version":"1.0","node_id":"node01","boot_id":"boot-example","sequence":12,"timestamp":null,"simulated":true,"event_type":"sensor_error","severity":"warning","detail":"temperature unavailable"}
```

sequence 引用相关样本；首批 event_type 为 sensor_error、network_recovered，severity 为 info/warning/error。阈值异常优先由确定性分析规则生成并标明来源，不逐条调用 LLM。不包含个人行为推断。此例为协议说明，尚无事件发布实现。

## 6. 控制（默认禁用，Planned）

v1 唯一拟开放操作是开发板低压 LED 状态反馈，禁止接市电、门锁、加热器等高风险执行器。

```json
{"schema_version":"1.0","node_id":"node01","command_id":"demo-001","action":"set_indicator","value":"on","ttl_seconds":10}
```

value 只接受 on/off。节点用接收时的单调时钟计 TTL（1–30 秒），避免依赖 RTC；它只能限制本地排队时间，不能证明网络中消息的新鲜性。因此 command **不得 retain**，节点使用 clean session，不缓存离线命令，仅支持幂等低风险操作；重复 command_id 不重复执行。过期/未知字段/未知动作拒绝并记录。控制实现前补充 Schema、拒绝测试及执行确认事件，当前不能拿此例宣称可控制。

Agent 只能通过 HA 已审核的服务控制实体，不能直接向 command Topic 发布。上线前人工确认目标实体与效果、限制域和服务，并准备本地物理停用方法；LLM 提示词不是权限边界。

## 7. 访问控制与变更

不允许匿名 Broker。每节点账号原则上仅写自身 telemetry/status/event、读自身 command；HA 可读取所有节点并写批准的 command；分析只读 telemetry/status/event。模拟阶段可使用独立实验 Broker，不能把共享开发账号带到真实运行环境。TLS 在跨机器/不可信网络接入前完成；未配 TLS 的 Compose 仅本机隔离调试。

新字段先讨论并更新契约版本与所有消费者；破坏性修改升级主版本，写迁移步骤。未支持版本明确拒绝，不静默解释。
