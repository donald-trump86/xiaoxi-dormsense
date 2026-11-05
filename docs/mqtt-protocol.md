# MQTT 通信协议 v1

状态：**v1.0 遥测契约与当前实现说明**。修改须经 PR、兼容性说明并同步 Schema、示例、固件、HA 与测试。周期遥测、事件和实验命令分开描述；事件和 C3 命令不能冒用遥测 Schema 的完整校验结论。

## 1. 命名与实际路径

前缀 `xiaoxi/dorm`，节点 ID 匹配 `node[0-9]{2,3}`。真实节点为 `node01` / `node02`，模拟器默认 `node90`；ID 不包含宿舍地址、姓名或学号。MQTT 客户端 ID 必须唯一。

| Topic | 当前路径 | 发布 QoS / Retain |
| --- | --- | --- |
| `xiaoxi/dorm/node01/telemetry` | UNO → 校验器 | 0 / 否 |
| `xiaoxi/dorm/node01/status` | UNO/LWT → 校验器 | 主动发布 0、LWT 1 / 是 |
| `xiaoxi/validated/node01/telemetry` | 校验器 → HA | 0 / 否 |
| `xiaoxi/validated/node01/status` | 校验器 → HA | 0 / 是 |
| `xiaoxi/dorm/node01/event` | UNO 按钮 → HA 事件实体 | 0 / 否 |
| `xiaoxi/dorm/node02/event` | C3 红外/诊断 → HA 事件实体 | 0 / 否 |
| `xiaoxi/dorm/node02/status` | C3/LWT → HA | 主动发布 0、LWT 1 / 是 |
| `xiaoxi/dorm/node02/command` | 受限的人工实验发布方 → C3 | 本项目历史单次测试使用 0 / 否；正式 ACL 不授予发布方 |
| `xiaoxi/dorm/node90/telemetry` 等 | 显式模拟器 → 开发模板 | 与真实数据分开，`simulated=true` |

UNO 周期遥测每 10 秒产生一次；QoS 0 接受丢失，不能称为可靠归档。订阅 QoS 1 也不能把 QoS 0 发布提升为 QoS 1；QoS 1 不等于恰好一次。默认不补传历史。

MQTT 3.1.1、UTF-8 JSON。接收端须限制体积、拒绝无效版本和 Topic/node_id 不一致，不让坏消息终止采集。当前真实周期遥测先经 [validator](../services/bridge/validator.py) 的严格解析、Schema/语义、来源与序号检查，再以原 payload 转发；持久状态是防重放高水位，不是遥测数据库。事件仍由独立模板作有限检查，没有宣称同等的完整事件 Schema 校验。

## 2. 周期遥测契约

机器契约为 [telemetry.schema.json](../schemas/telemetry.schema.json)，完整合成样例为 [telemetry.simulated.json](../data/samples/telemetry.simulated.json)。下例同样完全是模拟数据：

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
  "light": 0.5
}
```

上述九个字段必填，未知字段拒绝。Schema 另允许可选的 `rssi`、`uptime` 和 `sensor_status`；不能因为 JSON 可以扩展就自行增加业务字段。

| 字段 | 类型与语义 |
| --- | --- |
| schema_version | 固定字符串 `1.0` |
| node_id | 与原始 Topic 节点段一致 |
| boot_id | 每次启动的新 ID，1–64 位字母数字、`_` 或 `-`；须验证重启唯一性 |
| sequence | 非负整数，同一启动不复用；断线不复位；达到 2^32−1 前开启新 boot_id |
| timestamp | 已确认同步时才可使用 UTC RFC3339 `...Z`；未同步必须为 `null` |
| simulated | 合成输入 `true`，真实采样 `false`；不能以模拟数字补齐真实通道 |
| temperature | 摄氏度数值或 `null`；协议范围不代表传感器计量精度 |
| humidity | 相对湿度 0–100% 或 `null` |
| light | 0–1 无量纲相对亮度或 `null`，不是 lux；当前 LM393 为逆向 10 bit ADC 归一化 |
| rssi | 可选整数，−127 至 0 dBm |
| uptime | 可选非负整数，自启动经过的秒数 |
| sensor_status | 可选通道对象，值为 `ok`、`missing`、`error` |

未安装或读取失败仍保留通道并设为 `null`，不能以 0 伪装缺失；禁止 NaN/Infinity。存在 `sensor_status` 时，`ok` 对应数值、`missing/error` 对应 `null`。单位或通道语义改变须同步契约与消费者。

## 3. 时间、去重与缺失

当前节点不宣称已同步 UTC，`timestamp=null`。HA 实体属性中的 `received_at` 是 HA 接收消息的时间，不是设备精确测量时刻，状态变更时间也不等于最新采样时间。未来历史采集器应另存自己的 `{received_at, topic, payload}`，保留原 payload 和源时间质量；当前没有持续项目归档器。

周期遥测按 `(node_id, boot_id, sequence)` 去重；新 boot_id 切分运行段。同一运行段序号缺口可用于估计丢失，设备重启不能算成丢包。若同时归档事件，必须再按 Topic/消息流分开，因为 node01 事件序号与遥测序号独立。

断线后恢复发送当前样本，不提供持久离线缓存或补传。缺失应保留标记，不在原始层插值；没有可靠时钟同步不能以 `received_at - timestamp` 声称跨设备单向延迟，见[实验方案](experiments.md)。

## 4. 在线状态与 LWT

节点连接前设置 retained Last Will，连接后发送 online；主动离线与异常掉线要区分。合成状态例为：

```json
{"schema_version":"1.0","node_id":"node90","state":"offline"}
```

keepalive 为约 30 秒，实际 LWT 到达时间依网络与 Broker 行为而定，不能承诺瞬时离线。UNO 的 HA 周期实体还使用 35 秒 `expire_after`：旧 online 状态不能让旧温湿度继续被当成当前值。校验器握手、来源检查与可用状态转发的细节见[桥接说明](../services/bridge/README.md)。

仅清理被明确停用节点的 retained 状态，不广泛清空 Broker。事件实体记录最近事件，不能把其 `received_at` 当成周期心跳；事件过旧、不可用和周期读数过期是不同问题。

## 5. 已实现事件与剩余边界

当前 UNO 发布 `button_single_press`、`button_double_press`、`button_long_press_voice`；C3 发布接收、回环、预览、命令结果及拒绝等事件。共享包络包含版本、node_id、boot_id、该事件流 sequence、`timestamp=null`、`simulated`、event_type、severity 和 detail。下例只用于说明：

```json
{"schema_version":"1.0","node_id":"node01","boot_id":"example-only","sequence":12,"timestamp":null,"simulated":true,"event_type":"button_single_press","severity":"info","detail":"example_only"}
```

事件序号不是相关周期样本的引用。HA [事件模板](../home-assistant/mqtt/real/events.yaml)只做有限元数据检查并保留最近事件；它不证明消息通过完整 JSON Schema、物理手势全通过或空调确已响应。网关在事件不可用时清除投影中的旧事件内容。事件文本仅作数据，不授予控制或扩大访问权限。

阈值异常、稳定归档和提醒服务仍待实现；不逐条调用 LLM，不由事件推断住户作息或身份。

## 6. 控制：现有 C3 实验与只读系统分开

Hermes 仍只能经固定实体网关读取当前状态，没有设备控制服务、Broker 凭据或消息发布通路。正式 [Broker ACL](../deploy/examples/mosquitto-acl.conf)不给 HA 读取账户命令发布权；未来 Agent 控制必须另行完成经 HA 的细粒度执行与验收，不能靠改提示词启用。

C3 固件已有 `ac_preview` / `ac_send` 等实验命令，**没有本地 disarm 门禁**。预览不发射，真实发送选择单协议并调用一次 `sendAc()`；一次库调用可能生成多帧。启动载波校准与 NEC 自检也会发射，详见[C3 说明](../firmware/esp32-c3-ir/README.md)。

当前 C3 使用简化的字符串解析，TTL 仅检查 1–30 秒范围而非消息年龄，最近八个 command_id 仅在 RAM 去重。这些实现不满足完整严格 JSON、持久去重与过期拒绝目标。命令不得 retain，不自动补发或盲重试；已有一次人工授权发送记录不授权下一次发送。节点 ACK/本地回波不是空调状态回读。

旧的 `set_indicator` LED 命令仅是设计预留，不是本轮实现。未来受控路径需独立定义 Schema、授权有效期、幂等、审计、拒绝用例及物理停用方法；门锁、市电、加热负载不属于项目范围。

## 7. 访问控制与变更

不允许匿名 Broker。正式模板中节点只写自身状态/数据/事件并按需读自身命令，校验器只读原始 node01 遥测/状态并写对应 validated Topic，HA 读取账户仅订阅所需五类 Topic。真实板卡连接使用验证 CA/地址的 TLS 8883；1883 仅用于受控内部网络或显式本机开发，不作为 TLS 失败回退。

旧 [开发 Compose](../deploy/compose.yaml) 和 node90 模板保留原模拟用途，正式入口见[部署说明](deployment.md)。本轮没有更改既有生产账号或 ACL；模板权限不能当成现有实例权限已重新验收。

新增字段或动作先更新契约、版本、所有消费者和测试，破坏性变更给迁移步骤；未知版本明确拒绝，不静默解释。
