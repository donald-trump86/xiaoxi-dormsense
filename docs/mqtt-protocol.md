# MQTT 通信协议 v1

状态：**v1.0 遥测契约、C3 learn1 学习协议与当前实现说明**。修改须经 PR、兼容性说明并同步 Schema、示例、固件、HA 与测试。周期遥测、事件和实验命令分开描述；`learn1` 是 C3 的能力版本，外层 `schema_version` 仍为 `1.0`。事件和 C3 命令不能冒用遥测 Schema 的完整校验结论。

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
| `xiaoxi/dorm/node02/command` | 受限的人工实验发布方 / 本地学习服务 → C3 | 0 / 否；正式 ACL 不授予 HA 命令发布权 |
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

当前 UNO 发布 `button_single_press`、`button_double_press`、`button_long_press_voice`；C3 发布接收、回环、预览、命令结果、拒绝和 `ir_learning` 等事件。共享包络包含版本、node_id、boot_id、该事件流 sequence、`timestamp=null`、`simulated`、event_type、severity 和 detail。C3 实际事件保持 `schema_version="1.0"`、`node_id="node02"`、`simulated=false`；同一 boot 内全体事件共享 uint32 sequence，分包计算按模 2^32 处理回绕。下例只用于说明：

```json
{"schema_version":"1.0","node_id":"node01","boot_id":"example-only","sequence":12,"timestamp":null,"simulated":true,"event_type":"button_single_press","severity":"info","detail":"example_only"}
```

事件序号不是相关周期样本的引用。HA [事件模板](../home-assistant/mqtt/real/events.yaml)只做有限元数据检查并保留最近事件；它不证明消息通过完整 JSON Schema、物理手势全通过或空调确已响应。网关在事件不可用时清除投影中的旧事件内容。事件文本仅作数据，不授予控制或扩大访问权限。

C3 在显式学习窗口内发布 `ir_learning` 元数据和 `ir_raw_timing` 分包，沿用同一事件包络和 Topic。当前启动不再自动校准载波或发送 NEC，`ir_status` 也不发射。raw 每次导出保存缓冲的前 `min(rawlen, 300)` 项，每包最多 16 项；detail 仍为既有文本格式，携带 `capture`（首个 raw 分包 sequence）、`rawlen`、`kept`、`truncated`、`overflow`、`offset`、`count`、`unit=us` 和逗号分隔的 `times`。第 0 项统一为合成 2 μs 哨兵，不是实测空闲间隔；其余项按固定库的 2 μs tick 转换。后续包的 sequence 为 `(capture + offset/16) mod 2^32`。

历史启动 NEC 诊断最多保存 160 项；[离线分析器](../firmware/esp32-c3-ir/tools/nec_timing.py)继续接受这类历史截断记录，不能将其当成新上限下的完整波形。当前学习元数据先于 raw，complete 后仍可发布普通接收诊断；QoS 0 不保证送达，缺包、截断或溢出样本均不能当作完整学习成功。格式、历史 NEC 失败与合成分析边界见[C3 说明](../firmware/esp32-c3-ir/README.md)。现有 HA 模板只保存最近事件，不负责组装分包。

`ir_learning` 的 `detail` 是紧凑 JSON 的**字符串**，使用者须先解析外层包络，再解析该字符串；`ir_raw_timing.detail` 保留原文本格式，不能套用第二层 JSON 解析。固件统一转义 detail 中的引号、反斜杠和控制字符，拒绝超长输出而不截断 JSON。detail 上限 512 字节，完整输出缓冲 1024 字节（含字符串终止符）；命令 payload 上限 2560 字节，MQTT 缓冲 3072 字节。14 项标准状态随 capture 放在一个 detail 中，不另发 state 分包。

阈值异常、稳定归档和提醒服务仍待实现；不逐条调用 LLM，不由事件推断住户作息或身份。

## 6. 控制：现有 C3 实验与只读系统分开

Hermes 查询温湿度等当前状态仍走固定实体网关；新增本地学习能力须遵守下述边界，没有聊天发起的红外波形回放入口。正式 [Broker ACL](../deploy/examples/mosquitto-acl.conf)不给 HA 读取账户命令发布权；未来 Agent 设备控制必须另行完成经 HA 的细粒度执行与验收，不能靠改提示词启用。

C3 固件保留 `ac_preview` / `ac_send` 实验命令，**没有本地 disarm 门禁**。预览不发射；真实发送选择单协议并调用一次 `sendAc()`，期间暂停 RX，结束后 `enableIRIn(true)` 恢复；一次库调用可能生成多帧。`rx_paused=true` 是执行路径说明，不是零回波实测。当前启动移除了载波校准和自动 NEC；显式 `ir_loopback_test` / 串口诊断仍可能发射，详见[C3 说明](../firmware/esp32-c3-ir/README.md)。

本地[学习服务](../services/ir_learning/README.md)负责逐键学习、标准库交叉核对、UNKNOWN 人工确认和本地波形保存。新增固件学习/回放动作不向 Hermes 或聊天助手授予回放权限，也不改变 HA 的 Broker 发布权限。命令不得 retain，不自动补发或盲重试；已有一次人工授权发送记录不授权下一次发送。节点 ACK、`sent` 或本地回波均不是空调状态回读。

### 6.1 learn1 命令校验

新动作公共字段为 `schema_version:"1.0"`、`node_id:"node02"`、`action`、`command_id`、`ttl_seconds`。`command_id` / `session_id` 为 1–40 个 ASCII 字母、数字、`_` 或 `-`；主机使用 hex32。`ttl_seconds` 必须为整数 1–30。固件使用 ArduinoJson `6.21.5` 和有界语法检查，拒绝新动作的未知字段、重复字段、类型错误、超长或不完整输入；采用无字符串转义的规范 JSON 子集，不靠子串搜索识别新动作。

除 `ir_status` 外，下表所有新动作还必须带 `boot_id` 和 `deadline_ms`。boot 必须与当前启动一致；deadline 必须是 uint32 整数，并使 `int32(deadline_ms - millis())` 在 1–10000 ms。主机先以 status 的 `uptime_ms` 计算截止值，按 uint32 回绕处理，不能传 Unix 时间或仅凭 `ttl_seconds` 判断新鲜度。

| action | 公共字段及 boot/deadline 以外的字段 | 行为 |
| --- | --- | --- |
| `ir_status` | 无；也不接受 boot/deadline | 不发射，回当前能力版本与 uptime |
| `ir_learn_start` | `session_id`，整数 `window_seconds:1..60` | 清理/重启 RX，开启一个单帧窗口；已有窗口时拒绝 |
| `ir_learn_cancel` | `session_id` | 只取消匹配窗口，清理准备状态并恢复 RX |
| `ir_raw_prepare` | 整数 `frequency_khz:38`，整数数组 `timings_us` | 有界 RAM 准备，零发射，返回一次性 challenge |
| `ir_raw_commit` | `challenge`（小写 hex32） | 消费有效准备后发送一次，使用新的 `command_id` |

所有命令共享最近 8 个 `command_id` 的 RAM 去重表，重启即清空，不是持久幂等。新动作另用当前 boot/deadline 防止跨启动与过期请求，回放再加一次性 challenge。旧 `ac_preview` / `ac_send` / `ir_loopback_test` 也改用库解析，但其 TTL 仍只检查 1–30 秒范围，没有新增 boot/deadline 时效检查；不能把新动作的保证套用到旧入口。

### 6.2 学习窗口、状态与回执

成功回复使用 `event_type="ir_learning"`，detail 解析后字段如下。拒绝沿既有拒绝事件路径报告，不把拒绝当成成功回执。

| kind | detail 其余字段 |
| --- | --- |
| `status` | `command_id`，`version:"learn1"`，`uptime_ms:uint32` |
| `ready` | `session_id`，`command_id`，`window_seconds` |
| `capture` | `session_id`，`capture:uint32`，`protocol`（库名称），`bits`，`state`（对象或 `null`） |
| `complete` | `session_id`，`capture` |
| `cancelled` | `session_id`，`command_id` |
| `expired` | `session_id` |
| `prepared` | `command_id`，`challenge`（安全随机 hex32），`expires_ms:uint32` |
| `sent` | `command_id` |

学习只消费窗口内第一帧，在发布前清除 arm；到期或匹配取消分别发 `expired` / `cancelled`。同一帧先发 capture 元数据，再发 16 项一组、最多 300 项的 raw，最后发 complete。元数据事件的下一 sequence 就是 `capture`；complete 的 sequence 为 `(capture + ceil(kept/16)) mod 2^32`。主机按同一 boot、session、capture 关联，不将不同窗口拼接。收到 ready 只说明监听已开启；完整学习仍须核对连续分包、无溢出/截断和 complete。窗口内拒绝另一 start、真实 AC 发送、显式 NEC 和 raw 准备/提交，preview 仍不发射。

标准状态解码成功时，`state` 固定含 14 个键：`power`、`mode`、`temp_c`、`fan`、`swingv`、`swingh`、`light`、`turbo`、`econo`、`clean`、`sleep`、`ifeel`、`quiet`、`filter`。已支持的开关值为布尔，`temp_c` 为有限摄氏数值；模式、风速、摆风与 `sleep` 使用 stdAc 枚举/整数，不能按人类标签擅自重编号。不支持或不确定的字段必须为 `null`：GREE 的 `quiet` / `filter`；KELVINATOR 的 `econo` / `sleep` / `ifeel`；其他协议除已解出的 power/mode/temp/fan 外的额外字段。不能把库的公共默认 false/Auto 当成设备实际功能。无法解出标准状态则整个 `state=null`，包括 UNKNOWN。

保持 IRremoteESP8266 `2.9.0` 原始容差和严格 Kelvinator 优先顺序。GREE 只解出前 64 bit 时仍报告 `protocol="GREE"`、`bits=64`，并保留同次完整 raw；约 280 项 raw 不等于 128 bit 标准状态全部解码成功。主机对照库解码、原遥控器语义及人工确认决定是否保存记录；UNKNOWN 不会被固件自动猜成某个品牌。

### 6.3 原始波形准备与一次性提交

当前学习回放面向 38 kHz 的 GREE/KELVINATOR 记录。`timings_us` 不含 raw 第 0 项哨兵，必须为 15–299 项的奇数长度，逐项为 1–65535 μs 整数，总和不超过 1,000,000 μs；`frequency_khz` 只接受整数 `38`。固件只校验这些有界时序条件，不从 raw 自动确认协议身份；主机须完成记录来源、协议与人工确认检查。

prepare 只写 RAM，回 `prepared` 的安全随机 128 bit challenge（32 个小写十六进制字符），`expires_ms=(当前 uptime+10000) mod 2^32`。新 prepare 覆盖旧准备，开始新学习或取消匹配窗口时清理准备，过期后不能提交。状态查询不发射，也不替代 prepare。

commit 使用新的 command_id、当前 boot/deadline 和匹配 challenge；固件先消费并清空准备，再执行 `irrecv.disableIRIn()` → **一次** `irsend.sendRaw(..., 38)` → `irrecv.enableIRIn(true)`，无自动重试或额外 repeat。发送前已消费 challenge，即使随后发送路径失败也不能用旧 challenge 追加发送。返回 `sent` 只说明发送调用已执行，不表示空调开关、模式或温度已改变。

旧的 `set_indicator` LED 命令仅是设计预留，不是本轮实现。未来 Agent 受控路径仍需独立定义 Schema、授权有效期、幂等、审计、拒绝用例及物理停用方法；门锁、市电、加热负载不属于项目范围。

## 7. 访问控制与变更

不允许匿名 Broker。正式模板中节点只写自身状态/数据/事件并按需读自身命令，校验器只读原始 node01 遥测/状态并写对应 validated Topic，HA 读取账户仅订阅所需五类 Topic。真实板卡连接使用验证 CA/地址的 TLS 8883；1883 仅用于受控内部网络或显式本机开发，不作为 TLS 失败回退。

旧 [开发 Compose](../deploy/compose.yaml) 和 node90 模板保留原模拟用途，正式入口见[部署说明](deployment.md)。本轮没有更改既有生产账号或 ACL；模板权限不能当成现有实例权限已重新验收。

新增字段或动作先更新契约、版本、所有消费者和测试，破坏性变更给迁移步骤；未知版本明确拒绝，不静默解释。
