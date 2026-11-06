# 宿主机红外波形学习与安全回放服务（`services/ir_learning`）

本模块实现遥控器逐键波形学习、14 字段前后状态比对与私有存档。Hermes 可查询已存样本并按用户要求发射一次；HTTP 接口与本地 CLI 共用两阶段挑战码（Challenge-Commit）和持久化防重放逻辑。

---

## 1. 模块组成

| 文件路径 | 核心职责 |
| --- | --- |
| [model.py](model.py) | `LearningSession` 状态机：管理 45 秒单键采样窗口、280 边沿基准帧校验、前后两帧 14 字段比对、未知协议（`UNKNOWN`）人工标签归档及 `0700` 目录 / `0600` 原子文件持久化 |
| [transport.py](transport.py) | `CaptureCollector` 与 `LearningTransport`：通过 MQTT over TLS 8883（验证 CA 与主机名）连接 Broker，重组 `node02` 的 `ir_raw_timing` 分包并校验 `boot_id` 与单调递增序号 |
| [server.py](server.py) | 内部 HTTP 服务：Bearer Token 认证的 `POST /api/learning` 保留六个学习动作，`POST /api/control` 提供样本查询与单次发射 |
| [control.py](control.py) | `IRControl`：投影当前或指定档案的可用样本，阻止采样窗口内发射，并调用同一单次回放逻辑 |
| [replay.py](replay.py) | HTTP 与本地 CLI 共用的回放核心：校验私有样本、持久化操作编号，再执行 `ir_raw_prepare` 和 `ir_raw_commit` |

---

## 2. 可录键与推荐顺序

启动学习（`start`）会自动创建新的遥控器档案并开启 `baseline`（基准帧）采样窗口。完成基准帧后，推荐按以下顺序调用 `next` 逐键录制：

1. **核心控制键**：`power`（开关）、`mode`（模式）、`temp_up`（升温）、`temp_down`（降温）、`fan`（风速）、`swingv`（上下扫风）。
2. **可选功能键**：`swingh`、`light`、`sleep`、`turbo`、`clean`、`econo`、`ifeel`、`quiet`、`filter` 及自定义 `other`。

### 前后状态比对与防错按机制
- 当捕获到 `KELVINATOR`（128-bit）或 `GREE`（64-bit）已知协议帧时，`model.py` 会自动对比当前帧与上一帧的 14 个标准字段。
- 若用户误按了其它键（例如当前录制 `temp_up`，但实际改变的是 `mode`），服务会返回 `rejected` 并提示实际变化的字段，同时用刚收到的这帧更新比较基准，方便用户紧接着重按目标键。
- 若某键解码为 `UNKNOWN` 但脉冲分包完整，服务返回 `needs_confirmation`，由用户在对话中提供非空语义标签（`label`）并调用 `confirm(confirm=True, label=...)` 归档。

---

## 3. 样本查询与单次发射

`POST /api/control` 与学习接口使用同一 Bearer Token，仅开放以下动作：

| `action` | 参数与结果 |
| --- | --- |
| `list` | 可选 `profile_id`；默认当前档案，返回档案摘要、最多 128 条样本的完整解码状态与 `replayable`，以及本次操作的 `command_id`。不返回原始波形。 |
| `send` | 必须提供 `profile_id`、`record_id`、`command_id` 和严格布尔值 `confirm_once=true`；在学习接收窗口关闭后执行一次回放。 |

开关、模式、温度与风速共同构成目标状态。选择记录时核对 `state`，不能仅凭 `button="power"` 判断开机；UNKNOWN、无匹配载波或校验失败的波形不能发送。接口不接受调用方指定的路径、MQTT Topic、协议参数或脉冲数组。

发射共用 `replay_once`：先验证 38kHz 载波和脉冲边界，以 `O_CREAT | O_EXCL` 持久化操作编号，再向固定 `node02` 预装载波形，取得 10 秒有效的一次性 `challenge` 后提交一次。相同操作编号无法再次发送；超时或丢失回执时返回 `unknown_no_retry`，禁止自动换编号重试。`node_acknowledged` 只代表节点确认发射，`appliance_response_verified=false` 表示空调实际响应尚未核实。

本地操作者也可使用同一回放核心；先为下列三个变量填入本次查询得到的 32 位十六进制标识符，并将配置路径改为本机的私有文件：

```bash
source .venv/bin/activate
python -m services.ir_learning.replay \
  --config deploy/runtime/ir-learning/config.json \
  --profile "${IR_PROFILE_ID:?填入档案编号}" \
  --record "${IR_RECORD_ID:?填入样本编号}" \
  --command-id "${IR_COMMAND_ID:?填入本次操作编号}" \
  --confirm-once
```

---

## 4. 可选 Compose 部署与单元测试

在八容器安全栈中，可通过叠加 [deploy/compose.ir-learning.yaml](../../deploy/compose.ir-learning.yaml) 启动 `ir-learning` 容器。运行本模块 92 项离线测试：

```bash
source .venv/bin/activate
python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v
```
