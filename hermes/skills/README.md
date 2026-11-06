# Hermes 技能扩展目录（`hermes/skills`）

本目录用于存放面向交小西智能体的自定义 Markdown 技能包（`SKILL.md`）。

在当前工程基线中，核心宿舍能力已通过以下三种原生机制直接集成，无需手工加载额外技能脚本：
1. **工作区常驻规则**：[../workspace/AGENTS.md](../workspace/AGENTS.md)（自动注入环境查询、记忆管理与对话风格规范）。
2. **Home Assistant 只读状态工具**：内置 `ha_get_state` 与 `ha_list_entities`，直接对接 `read-gateway:8080`。
3. **原生空调红外学习插件**：[../plugins/xiaoxi_ir_learning/README.md](../plugins/xiaoxi_ir_learning/README.md)。
