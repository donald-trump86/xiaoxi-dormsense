# 逐键红外学习服务

这个服务连接 Hermes 的[原生学习插件](../../hermes/plugins/xiaoxi_ir_learning/README.md)与固定的 `node02` 红外节点。Hermes 只能请求打开接收窗口、读取学习摘要和记录按键解释；原始时序由服务校验并保存在私有状态卷。Home Assistant 查询继续走原有只读网关。

## 当前验收状态

2026-11-05 已部署专用服务、原生插件和配置；在原七个角色上增加 `ir-learning`，共八个角色。C3 目标编译及唯一一次真实 USB 上传均退出 0。最初检查因节点尚未重连返回 `receiver_not_ready`；后续独立 TLS 状态查询已确认在线，返回 `learn1`、启动 ID `node02-00000016`。

官方活动 profile 的原生目录已确认注册三个学习工具。Hermes 默认通过 `tool_search`、`tool_describe`、`tool_call` 延迟呈现插件工具，不能要求三个名称直接出现在初始 schema 列表。真实 `deepseek-chat` 新会话已先描述工具，再调用 `xiaoxi_ac_learning_status`，返回空闲并用中文回答。浏览器交互、原装遥控器逐键实录、学习后回放和空调响应仍待验收。

## 学习接口与对话入口

[HTTP 服务](server.py)仅接受带独立 Bearer 凭据的 `POST /api/learning`。JSON 请求最多 2048 字节，只允许下表六种动作及其相关字段；未知动作、额外字段、重复 JSON 键和非有限数值会被拒绝。

| 动作 | 参数 | 行为 |
| --- | --- | --- |
| `start` | 无 | 新建 profile 并准备 `baseline` 接收；已有未取消的 profile 时只返回现状，不重复打开窗口 |
| `next` | `button` | 为一个键打开 45 秒接收窗口；节点应答就绪后才提示按键 |
| `status` | 无 | 返回当前学习摘要，不向节点发命令 |
| `confirm` | `button`、`confirm: true`、非空 `label` | 只对待人工说明的样本记录解释；`button` 必须与当前键一致，不发送红外 |
| `skip` | `button`，可选 `reason` | 仅跳过匹配的当前键，清除待确认样本或当前接收窗口，保留已存记录 |
| `cancel` | 无 | 停止当前初始化并保留已存记录；此后再 `start` 会新建 profile，旧文件保留 |

插件只注册三个原生工具，属于 `xiaoxi_ir_learning` 工具集：

| 工具 | 映射 |
| --- | --- |
| `xiaoxi_ac_initialize` | `action` 为 `start`（默认）、`status` 或 `cancel` |
| `xiaoxi_ac_learn_key` | 必须指定 `button`；`capture`（默认）映射 `next`，另支持 `confirm`、`skip` |
| `xiaoxi_ac_learning_status` | 无参数，映射 `status` |

操作时先说明遥控器当前显示，等待 `ready` 后将遥控器对准 C3 接收头、避开空调，按一次指定键。随后查询状态，核对遥控器显示与受支持的解码字段，避免密集轮询。`receiver_not_ready` 表示窗口尚未准备成功，不能据此提示用户开始按键。

服务启动是被动的：恢复私有状态，连接 MQTT TLS 并订阅节点状态与事件，不会自动打开学习窗口或发射红外。`GET /health` 只检查 HTTP 服务能响应，不能证明 MQTT、node02 或接收头就绪。返回的学习状态可能是 `idle`、`arming`、`ready`、`captured`、`needs_confirmation`、`rejected`、`expired` 或 `cancelled`。

## 可录键与推荐顺序

[学习模型](model.py)接受 17 个键标识，其中 `baseline` 是基线步骤，`other` 用于补录特殊键。`recommended_buttons` 按下表中的推荐顺序返回 11 个常用键；推荐不表示遥控器一定有这个键。

| 标识 | 含义 | 推荐顺序 |
| --- | --- | --- |
| `baseline` | 当前设置的基线样本 | 开始前必需，不列入推荐键 |
| `power` | 开关 | 1 |
| `mode` | 模式 | 2 |
| `temp_up` | 温度＋ | 3 |
| `temp_down` | 温度－ | 4 |
| `fan` | 风速 | 5 |
| `swingv` | 上下扫风 | 6 |
| `swingh` | 左右扫风 | 7 |
| `light` | 屏显／灯光 | 8 |
| `sleep` | 睡眠 | 9 |
| `turbo` | 超强 | 10 |
| `clean` | 干燥／自清洁，具体含义依遥控器而定 | 11 |
| `econo` | 节能 | 按需 |
| `ifeel` | 感温／随身感 | 按需 |
| `quiet` | 静音 | 按需 |
| `filter` | 健康／过滤 | 按需 |
| `other` | 其他特殊键，由用户说明名称 | 按需 |

没有的键可跳过。温度键处于上限或下限时，先调整并重新建立基线。服务重启、接收超时、样本不完整，或在接收中跳过后，状态上下文不再可靠；应先请求录制 `baseline`，再录其他键。每个 profile 最多保存 128 条记录，同一键可保留多次样本。

## 完整波形与解释的边界

当前配置以 `expected_rawlen: 280` 校验完整状态样本，不能因为库只解出首段就接受 140 项的短样本。[分包收集器](transport.py)的保留上限为 300 项，并检查节点、启动 ID、会话、capture ID、序号、分片偏移及完整性。缺片、重复片、溢出或截断都会使本次接收失效。时序使用正偶数微秒值，首项为归一化的 `2` 微秒占位，不代表实测载波频率。

协议库解出状态时，模型只比较按键前后都支持且非 `null` 的字段。目标字段没有变化，或温度方向不符，样本不会绑定到所请求的键。按错键仍可能改变遥控器的当前状态，后续比较会使用最新收到的状态。

`GREE`、64 bit 且长于 140 项的样本标为 `partial_protocol`：库只识别首段，服务保留完整波形并返回扩展段未校验的警告。不能把首段解码结果当成整帧语义已验证。解调接收头不测量载波频率；本地重放只接受已建立标称 38 kHz 的记录。UNKNOWN 及缺少该协议依据的记录可以暂存，但会在网络连接、intent 或 prepare 之前拒绝重放。

`UNKNOWN` 没有经过验证的解码状态，符合长度和分包约束也不能证明其物理协议完整。用户必须说明实际按键名称并同意暂存，才能确认人工标签。记录使用 `semantic_source: user_report_unverified` 和 `semantics_verified: false`；`confirm: true` 只记录这次解释，不构成独立的人类批准证据，也不会发射红外。缺失或协议不支持的字段保持未知或 `null`，不能替换成 `false`。所有学习记录均保留 `appliance_response_verified: false`。

## 私有存储与身份

状态目录由私有配置的 `state_dir` 指定，compose 中应为 `/state`。目录由服务运行用户拥有，权限为 `0700`；写入的 profile、活动索引和重放日志权限为 `0600`。服务以临时文件、文件 `fsync` 和替换保存学习状态。重启后保留已存按键，旧接收窗口不恢复，并要求重新建立基线。

profile 文件以小写 32 位十六进制 ID 命名，保存原始时序、前后状态、人工标签及验证依据；活动索引为 `active.json`。HTTP 和工具结果只返回受限摘要，省略完整时序。私有文件不应进入仓库、聊天、模型上下文或通用工具参数。

本地重放会额外检查配置和所选 profile 是当前有效用户拥有的普通 `0600` 文件，状态目录为同一用户拥有的 `0700` 目录，并拒绝末级符号链接。因此操作者必须采用与挂载配置、状态一致的属主身份；不能任意代入宿主用户的 UID。

## 可选 compose 部署

[compose 文件](../../deploy/compose.ir-learning.yaml)只定义学习服务，连接已有的 backend 与 agent 外部网络，不改 Hermes 或 Home Assistant 的网络。Hermes 保持在 agent 网络，通过 `http://ir-learning:8090/api/learning` 请求摘要；学习服务单独持有固定 node02 所需的 MQTT 权限。Hermes 不获取 MQTT 凭据、HA 后端凭据或 backend 网络入口。

服务以 `10001:10001` 运行，根文件系统与代码、配置挂载只读，状态卷可写，无宿主端口映射。运行时镜像须已包含项目所需 Python 依赖，并提供 Python `ENTRYPOINT`，因为 compose 的命令从 `-B -m ir_learning.server` 开始。配置目录必须预先存在；其中的 `config.json` 为 `0600`，在容器内由 UID 10001 拥有并可读取，目录可由该用户遍历。服务 API 凭据与 Hermes 活动 profile 中的 `XIAOXI_IR_LEARNING_TOKEN` 对应，独立于 HA 凭据。

以下均为供另行授权操作时使用的占位示例，本轮文档工作没有执行。先替换镜像、私有目录、网络及卷名；不要把秘密写入这些示例或终端参数：

```bash
export XIAOXI_IR_RUNTIME_IMAGE='<reviewed-python-runtime-image>'
export XIAOXI_IR_LEARNING_CONFIG_DIR='<absolute-private-config-directory>'
export XIAOXI_IR_LEARNING_VOLUME='<external-state-volume>'
export XIAOXI_BACKEND_NETWORK='<existing-backend-network>'
export XIAOXI_AGENT_NETWORK='<existing-agent-network>'
```

外部卷不会由 compose 自动创建。仅对首次创建的空状态卷预置属主和权限；已有状态卷应保留原数据及属主：

```bash
docker volume create "${XIAOXI_IR_LEARNING_VOLUME:?}"
docker run --rm --network none --read-only --user 0:0 \
  --cap-drop ALL --cap-add CHOWN --entrypoint python \
  --mount "type=volume,source=${XIAOXI_IR_LEARNING_VOLUME:?},target=/state" \
  "${XIAOXI_IR_RUNTIME_IMAGE:?}" -B -c \
  'import os; os.chmod("/state", 0o700); os.chown("/state", 10001, 10001)'
```

从仓库根目录启动这个可选服务：

```bash
docker compose -f deploy/compose.ir-learning.yaml up -d ir-learning
```

默认外部网络名为 `deploy_default`、`deploy_agent`，默认卷名为 `deploy_ir-learning-data`；上述变量可显式选择已有资源。健康检查成功后，仍需分别验收新会话工具目录、模型调用、节点在线、接收就绪和真实收帧，不能用 HTTP 健康结果替代。

## 可信本地操作者的单次重放

[本地重放命令](replay.py)只供可信操作者使用。HTTP 六动作和原生三个工具都没有重放入口；Hermes 不接收下列参数，也不应获得可执行此命令的通用终端或代码工具。学习与标签确认不触发重放。

配置和状态挂载属主均为 UID 10001 时，可由操作者采用同一 compose 配置启动一次性进程。下面的 `profile`、`record` 和全新 `command-id` 都必须替换为小写 32 位十六进制值；`--confirm-once` 明确授权这一次提交尝试。此示例会在真正执行后尝试发射红外，本轮未授权、未执行：

```bash
docker compose -f deploy/compose.ir-learning.yaml run --rm --no-deps \
  --user 10001:10001 ir-learning \
  -B -m ir_learning.replay --config /run/learning/config.json \
  --profile '<saved-profile-hex32>' --record '<saved-record-hex32>' \
  --command-id '<new-attempt-hex32>' --confirm-once
```

命令读取所选记录的快照，不构造学习会话，也不修改 profile。默认要求完整 280 项样本，受配置的 `expected_rawlen` 约束；总上限 300 项。跳过首项占位后，重放时序必须为 15–299 项奇数长度、每项不超过 65535 微秒、总时长不超过 1000000 微秒，且无溢出或截断。

在连接 MQTT 前，命令以排他创建方式预留 `replay-<command-id>.json`；已存在的 ID 会在任何新连接或发布前拒绝。准备阶段核对当前启动 ID、节点时间、挑战值和有效期，不发射红外。提交前先将日志更新为 `commit_consumed` 并对文件和目录 `fsync`，再至多发布一次 QoS 0、非 retained 的提交。超时或 ACK 不明时不重试，不删除日志来复用 ID。

退出码 `0` 表示节点 ACK，`2` 表示检查拒绝或不可用，`3` 表示提交结果不明。即使退出 0，结果仍为 `appliance_response_verified: false`；节点 ACK 不能证明空调响应。结果不明时，应先由操作者核对实际状态和日志，不能自动换一个 ID 补发。

## 离线检查

从仓库根目录使用现有虚拟环境，可运行：

```bash
.venv/bin/python -B -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v
.venv/bin/python -B -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v
```

本轮主代理实际执行 52 项服务/会话/组包/HTTP/回放离线用例和 14 项插件用例，全部通过；另有固件 22 项主机用例、13 项 native 用例、目标编译与唯一一次 USB 上传记录。真实模型状态查询是独立的运行时证据。离线用例不证明实际收帧、载波或空调行为，文中的真实回放示例尚未执行。
