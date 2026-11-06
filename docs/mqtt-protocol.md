# MQTT v1 通信协议与数据契约

本文定义 **XiaoXi DormSense** 中感知节点（`node01`）、红外节点（`node02`）、契约验证器（`validator`）、Home Assistant 与红外学习服务（`ir-learning`）之间的 MQTT Topic 命名规范、JSON 消息格式及可靠性约定。

---

## 1. Topic 命名空间与权限矩阵

所有 Topic 均使用小写 ASCII 字符，层级结构如下：

```text
xiaoxi/dorm/<node_id>/telemetry        # 节点原始周期遥测 (node01, node90)
xiaoxi/dorm/<node_id>/status           # 节点在线状态与遗嘱 LWT (retained)
xiaoxi/dorm/<node_id>/event            # 节点离散事件：按钮手势、红外收发、学习分包
xiaoxi/dorm/<node_id>/command          # 主机下发给节点的控制或学习命令 (node02)
xiaoxi/validated/<node_id>/telemetry   # 经 validator 校验通过的遥测 (供 HA 订阅)
xiaoxi/validated/<node_id>/status      # 经 validator 校验通过的在线状态 (retained)
```

### 节点编号与账号 ACL 隔离（[mosquitto-acl.conf](../deploy/examples/mosquitto-acl.conf)）

| 账号 / 身份 | 对应节点 / 服务 | 允许写入（`write`） | 允许读取（`read`） |
| --- | --- | --- | --- |
| `xiaoxi_node01` | UNO R4 WiFi（真实环境节点） | `xiaoxi/dorm/node01/{telemetry,status,event}` | 无（纯上报节点，不订阅任何命令） |
| `xiaoxi_node02` | ESP32-C3（真实红外节点） | `xiaoxi/dorm/node02/{status,event}` | `xiaoxi/dorm/node02/command` |
| `xiaoxi_validator` | `node01-validator` 验证服务 | `xiaoxi/validated/node01/{telemetry,status}` | `xiaoxi/dorm/node01/{telemetry,status}` |
| `xiaoxi_ha_read` | Home Assistant 平台 | 无（只读账号） | `xiaoxi/validated/node01/#`、`xiaoxi/dorm/node01/event`、`xiaoxi/dorm/node02/{status,event}` |
| `xiaoxi_ir_learning` | `ir-learning` 学习与回放服务 | `xiaoxi/dorm/node02/command` | `xiaoxi/dorm/node02/{status,event}` |
| `xiaoxi_dev` | 本地模拟器（`node90`） | `xiaoxi/dorm/node90/{telemetry,status}` | `xiaoxi/dorm/node90/{telemetry,status}` |

---

## 2. 传输参数与可靠性约定

| 消息类别 | 发布周期 / 触发条件 | QoS | Retained | 过期与保活策略 |
| --- | --- | --- | --- | --- |
| `telemetry`（周期遥测） | 每 **10 秒** 1 帧 | `0` | `false` | HA 侧配置 `expire_after: 35`（约 3.5 个采样周期未收到新帧即标为 `unavailable`） |
| `status`（在线状态 / LWT） | 连接成功时发 `online`，断连由 Broker 触发 LWT 发 `offline` | `1`（LWT） | `true` | MQTT `keepalive: 30` 秒，断电或 Wi-Fi 中断后约 30–45 秒内自动切为离线 |
| `event` / `command` | 按钮触发、红外收发、学习采样 | `0` | `false` | 命令禁止设置 `retained=true`，防止节点重连时误执行历史命令 |

---

## 3. 周期遥测消息契约（`telemetry`）

完整 JSON Schema 位于 [schemas/telemetry.schema.json](../schemas/telemetry.schema.json)（`additionalProperties: false`），并由 [check_repository.py](../scripts/check_repository.py) 与 [validator.py](../services/bridge/validator.py) 强制执行跨字段校验：

```json
{
  "schema_version": "1.0",
  "node_id": "node01",
  "boot_id": "node01-00000009",
  "sequence": 500,
  "timestamp": null,
  "uptime_s": 5012,
  "simulated": false,
  "temperature": 22.8,
  "humidity": 53.3,
  "light": 0.642,
  "sensor_status": {
    "temperature": "ok",
    "humidity": "ok",
    "light": "ok"
  }
}
```

### 关键字段设计说明

- **`boot_id` 与 `sequence`**：微控制器无电池供电的实时时钟（RTC），刚上电时未必完成 NTP 授时（此时 `timestamp` 置为 `null`）。固件利用片上 EEPROM 记录递增的启动编号生成 `boot_id`，配合每次启动从 `0` 单调递增的 `sequence`，构成全局唯一的样本主键 `(node_id, boot_id, sequence)`，供后端去重与乱序识别。
- **缺测与 `sensor_status` 联动**：若某路传感器未就绪或读取超时，对应状态填 `"missing"` 或 `"error"`，且数值字段必须为 `null`（禁止用 `0`、`-999` 或旧读数填充）；当状态为 `"ok"` 时，数值字段必须为合法范围内的有限浮点数（`temperature: -40~85°C`，`humidity: 0~100%`，`light: 0.0~1.0`）。

---

## 4. 在线状态消息（`status`）

发布至 `xiaoxi/dorm/<node_id>/status`（经验证器转发至 `xiaoxi/validated/node01/status`）：

```json
{
  "schema_version": "1.0",
  "node_id": "node01",
  "state": "online",
  "boot_id": "node01-00000009",
  "uptime_s": 12
}
```

Broker 登记的遗嘱消息（LWT）固定为：`{"schema_version":"1.0","node_id":"node01","state":"offline"}`。

---

## 5. 离散事件消息（`event`）

`node01` 与 `node02` 的离散事件均发布至 `xiaoxi/dorm/<node_id>/event`，统一包络结构如下：

```json
{
  "schema_version": "1.0",
  "node_id": "node01",
  "boot_id": "node01-0000000c",
  "sequence": 14,
  "timestamp": null,
  "simulated": false,
  "event_type": "button_single_press",
  "detail": "gesture=single scene=1 lines=1,1,0"
}
```

### 常用 `event_type` 列表

- **`node01`（按钮手势事件）**
  - `button_single_press`：单击按钮，切换板载 12×8 LED 点阵显示场景。
  - `button_double_press`：双击按钮，网页端可联动发起温湿度光照播报。
  - `button_long_press_voice`：长按按钮（≥ 700 ms），点阵屏进入 10 秒声波跳动动画，网页端可联动开启语音收音。
- **`node02`（红外诊断与学习事件）**
  - `ir_remote_captured`：普通模式下捕获到红外帧（`detail` 含 `proto=`、`bits=`、`rawlen=`、`code=` 及 `ac=` 摘要）。
  - `ir_raw_timing`：原始微秒脉冲分包数据（每包最多 16 项时长，最高保留 300 项，供 `nec_timing.py` 或 `ir-learning` 组包还原完整波形）：
    `raw_timing capture=<seq> rawlen=<N> kept=<K> truncated=<0|1> overflow=<0|1> offset=<idx> count=<M> unit=us times=<t0,t1,...>`
  - `ir_learning`：`learn1` 学习协议的结构化回执（`detail` 为 JSON 字符串，见第 6 节）。

---

## 6. ESP32-C3（`node02`）命令与 `learn1` 学习回放协议

主机向 `xiaoxi/dorm/node02/command` 发送非保留（`retained=false`）命令。

### 6.1 learn1 命令校验

`learn1` 协议包含 5 类动作，采用 ArduinoJson 严格解析，拒绝未知字段、重复键与越界数值。除 `ir_status` 探针外，其余 4 类动作均要求匹配当前节点的 `boot_id` 与基于设备单调时钟 `millis()` 计算的 `deadline_ms`（剩余有效期必须在 `1..10000` ms 内），且 `ttl_seconds` 介于 `1..30`、最近 8 个 `command_id` 在 RAM 中去重：

| `action` | 必填字段 | 功能与节点行为 |
| --- | --- | --- |
| `ir_status` | `command_id`, `ttl_seconds` | 非发射状态探针：返回 `version: "learn1"`、当前 `boot_id` 与设备 `uptime_ms` |
| `ir_learn_start` | `command_id`, `session_id`, `window_seconds` (`1..60`), `boot_id`, `deadline_ms`, `ttl_seconds` | 开启单帧学习窗口：清理接收缓冲并回 `ready`；收到第一帧红外信号后依次发布 `capture` 元数据（含 14 个标准空调状态字段）、`ir_raw_timing` 脉冲分包（最多 300 项）与 `complete` 完成事件 |
| `ir_learn_cancel` | `command_id`, `session_id`, `boot_id`, `deadline_ms`, `ttl_seconds` | 取消当前活动的学习窗口并返回 `cancelled` |
| `ir_raw_prepare` | `command_id`, `boot_id`, `deadline_ms`, `ttl_seconds`, `frequency_khz` (`38`), `timings_us`（`15..299` 项奇数长正整数数组，总和 `<= 1,000,000` μs） | 预装载待发送的原始微秒脉冲序列（不发射红外），生成 10 秒有效期的随机 32 位十六进制一次性 `challenge` |
| `ir_raw_commit` | `command_id`, `boot_id`, `deadline_ms`, `ttl_seconds`, `challenge` | 校验并消费一次性 `challenge`，暂停接收中断（`disableIRIn()`），调用 `sendRaw(..., 38)` 发射一次原始波形后恢复接收（`enableIRIn(true)`），返回 `sent` |

此外，固件兼容标准库协议预览命令 `ac_preview`（仅校验参数而不发射红外）、标准库发送命令 `ac_send` 与光学回环诊断命令 `ir_loopback_test`。完整实现详见 [ir_learning.h](../firmware/esp32-c3-ir/include/ir_learning.h) 与 [ir-learning 服务说明](../services/ir_learning/README.md)。
