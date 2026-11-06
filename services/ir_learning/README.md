# 宿主机红外波形学习与安全回放服务（`services/ir_learning`）

本模块实现空调遥控器逐键波形学习的会话管理、14 字段前后状态防呆比对、私有持久化存储以及受控的两阶段挑战码（Challenge-Commit）回放 CLI。

---

## 1. 模块组成

| 文件路径 | 核心职责 |
| --- | --- |
| [model.py](model.py) | `LearningSession` 状态机：管理 45 秒单键采样窗口、280 边沿基准帧校验、前后两帧 14 字段比对、未知协议（`UNKNOWN`）人工标签归档及 `0700` 目录 / `0600` 原子文件持久化 |
| [transport.py](transport.py) | `CaptureCollector` 与 `LearningTransport`：通过 MQTT over TLS 8883（验证 CA 与主机名）连接 Broker，重组 `node02` 的 `ir_raw_timing` 分包并校验 `boot_id` 与单调递增序号 |
| [server.py](server.py) | 面向内部 `agent` 网段的 HTTP 服务（`POST /api/learning`，Bearer Token 认证），向 Hermes 插件开放 `start`、`next`、`status`、`confirm`、`skip`、`cancel` 六个学习动作 |
| [replay.py](replay.py) | 本地操作者专用的单次回放 CLI：读取已归档的原始微秒波形，在写入本地防重放日志后依次执行 `ir_raw_prepare` 与 `ir_raw_commit` |

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

## 3. 可信本地操作者的单次重放

为保证安全边界，HTTP 学习接口与 Hermes 对话插件不包含红外发射动作。需要回放已录制的按键波形时，在宿主机执行 `replay.py`：

```bash
source .venv/bin/activate
python -m services.ir_learning.replay \
  --config deploy/runtime/ir-learning/config.json \
  --profile-id <32位十六进制profile_id> \
  --button power \
  --operator-intent ac-test-001
```

`replay.py` 会先校验目标记录的载波频率（38kHz）与脉冲数组合法性，在私有目录下以 `O_CREAT | O_EXCL` 写入单次意图文件，随后向 `node02` 发送 `ir_raw_prepare` 获取 10 秒有效期的随机 `challenge`，最后发送 `ir_raw_commit` 触发单次 38kHz 原始波形发射。

---

## 4. 可选 Compose 部署与单元测试

在八容器安全栈中，可通过叠加 [deploy/compose.ir-learning.yaml](../../deploy/compose.ir-learning.yaml) 启动 `ir-learning` 容器。运行本模块 52 项单元测试：

```bash
source .venv/bin/activate
python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v
```
