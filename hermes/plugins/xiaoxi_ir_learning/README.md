# 交小西空调红外学习插件（`xiaoxi_ir_learning`）

本目录是 Hermes 原生插件 `xiaoxi_ir_learning` 的源码目录，通过调用内部网段 `http://ir-learning:8090/api/learning`（参见 [services/ir_learning/README.md](../../../services/ir_learning/README.md)），让用户能够直接用自然语言完成原装空调遥控器的逐键波形学习。

---

## 1. 插件注册的三个对话工具

| 工具名称 | 功能与参数说明 |
| --- | --- |
| `xiaoxi_ac_initialize` | 创建新的遥控器学习档案并自动开启 45 秒的 `baseline`（基准帧）采样窗口 |
| `xiaoxi_ac_learn_key` | 对指定按键执行动作：`action` 支持 `next`（开启目标按键 45 秒采样窗口）、`confirm`（为 `UNKNOWN` 波形确认人工语义标签 `label`）、`skip`（跳过当前遥控器没有的按键）、`cancel`（取消当前采样窗口） |
| `xiaoxi_ac_learning_status` | 查询当前学习会话状态、已录制的按键列表、最新一帧的 14 字段解码摘要与前后变化字段 |

---

## 2. 安全设计与单元测试

- **凭据按需读取**：每次请求通过 Hermes 官方 `get_secret("XIAOXI_IR_LEARNING_TOKEN")` 获取 Bearer Token，不向模型上下文泄露凭据或原始微秒数组。
- **学习与发射分离**：插件仅支持固定学习动作（`start`、`next`、`status`、`confirm`、`skip`、`cancel`），不包含任何红外回放发射接口。

运行本插件的 14 项单元测试：

```bash
source .venv/bin/activate
python -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v
```
