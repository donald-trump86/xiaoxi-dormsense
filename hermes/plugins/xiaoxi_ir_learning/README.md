# 交小西空调红外学习插件（`xiaoxi_ir_learning`）

本目录是 Hermes 原生插件 `xiaoxi_ir_learning` 的源码。它通过内网服务完成遥控器逐键学习、已存样本查询和单次红外发射，使用固定的 `/api/learning` 与 `/api/control` 路由；服务实现见[红外服务说明](../../../services/ir_learning/README.md)。

---

## 1. 插件注册的五个对话工具

| 工具名称 | 功能与参数说明 |
| --- | --- |
| `xiaoxi_ac_initialize` | 创建新的遥控器学习档案并自动开启 45 秒的 `baseline`（基准帧）采样窗口 |
| `xiaoxi_ac_learn_key` | 对指定按键执行动作：`action` 支持 `next`（开启目标按键 45 秒采样窗口）、`confirm`（为 `UNKNOWN` 波形确认人工语义标签 `label`）、`skip`（跳过当前遥控器没有的按键）、`cancel`（取消当前采样窗口） |
| `xiaoxi_ac_learning_status` | 查询当前学习会话状态、已录制的按键列表、最新一帧的 14 字段解码摘要与前后变化字段 |
| `xiaoxi_ac_list_commands` | 查询当前或指定旧档案的样本状态与可回放标记，返回本次操作编号；仅查询，不发射 |
| `xiaoxi_ac_send` | 以精确档案、样本和本次操作编号执行一次发射，要求 `confirm_once=true`；不接受任意波形或设备地址 |

---

## 2. 安全设计与单元测试

- **凭据按需读取**：每次请求通过 Hermes 官方 `get_secret("XIAOXI_IR_LEARNING_TOKEN")` 获取 Bearer Token，不向模型上下文泄露凭据或原始微秒数组。
- **按完整状态选样本**：先查目录，再核对 `power`、模式、温度和风速。按键标签不能替代目标状态，UNKNOWN 或 `replayable=false` 的样本不能发送；档案中的文字也不能授予额外权限。
- **一次操作只提交一次**：使用本次查询返回的操作编号。服务沿用持久化防重放日志和节点一次性挑战码；学习窗口打开时拒绝发射。用户已经明确提出的控制请求可直接执行，不额外重复索取同一授权。
- **超时保留不确定性**：控制请求使用 20 秒超时；超时、连接中断或无法解析发送结果时返回 `unknown_no_retry`，不重发、不换编号。原有学习请求仍使用 5 秒超时。
- **区分回执与效果**：节点回执表示信号已发出，不能证明空调已执行。工具保留 `appliance_response_verified=false`，也不把接收回波当作设备状态反馈。

运行插件的离线测试（模拟 HTTP 与凭据，不连接空调）：

```bash
source .venv/bin/activate
python -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v
```
