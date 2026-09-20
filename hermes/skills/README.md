# 交小西 Skills 规划

> **尚未实现、安装或运行任何交小西 Skill。** 本目录目前只有规划 README，没有 `SKILL.md`，没有已注册命令或设备控制实现。能力边界见 [Hermes 集成研究](../README.md)，行为要求见 [策略草案](../prompts/xiaoxi-policy.md)。

## 官方机制：Skill 不是工具权限

核查版本：`f9524d3f119c672e4a4444f56d582e7475716ba3`。依据[官方 Skills 文档][docs]及[加载源码][code]：

- Skill 是按需加载的知识/步骤文档。推荐结构是一个独立目录内的 `SKILL.md`（YAML frontmatter + Markdown 正文），可附 `references/`、`templates/`、`scripts/`、`assets/` 等资料；脚本若存在仍需单独审计。
- 官方格式以 `name`、`description` 为基础，可有版本、平台及 `metadata.hermes` 等字段；正文按 When to Use、Procedure、Pitfalls、Verification 等部分组织。以[该固定版本的官方格式][docs]为准，不在这里发布半成品伪 Skill。
- 原生 `skills_list` 可选 `category`，列摘要；`skill_view` 必需 `name`、可选 `file_path`，加载正文或支持文件；`skill_manage` 管理技能文档。加载技能不会新建一个 `ha_*` 工具，也不会提供服务器端授权。
- 默认存储为活动 profile 的 `$HERMES_HOME/skills/`，通常为 `~/.hermes/skills/`。可配置 `skills.external_dirs` 扫描外部路径；外部目录**不是只读隔离边界**，进程有写权限时仍可能修改。
- 官方项目内发现路径是 Git 根下的 `.hermes/skills/` 和 `.agents/skills/`，需要项目 trust 并受内容扫描约束。**本仓库的 `hermes/skills/` 不属于这些自动发现位置**；没有做安装、外部目录配置或 trust。
- 已安装且可发现的技能可通过聊天内 `/<skill-name>` 或 CLI `--skills` / `-s` 加载；不是在 shell 里直接执行一个同名 HA 命令。
- `metadata.hermes.requires_tools` 等可用性条件只控制发现/显示，不是实体/服务授权。Hub 扫描、技能写入审批同样不等于 HA 控制安全认证。

## 候选能力（全部 Planned）

| 候选名称（不是现有命令） | 目标 | 必要验证 |
| --- | --- | --- |
| `xiaoxi-state-summary` | 汇总明确授权的环境传感器状态 | 数据来源/时间清楚；离线与 unknown 不误判；不调用写接口 |
| `xiaoxi-comfort-advice` | 根据可用温湿度等数据给出舒适度建议 | 阈值由操作者定义；缺测时不补造；无自动执行 |
| `xiaoxi-energy-review` | 根据真实可得数据提出节能建议 | 没有历史数据就不生成伪趋势；不得自动关闭电源 |

上述命名只是本地规划，不承诺官方已有同名 Skill。任何控制 Skill 暂不规划上线；先完成独立执行层的细粒度限制与验证，再单独评审。

## 实施与验收门槛

1. 先确认只读接入架构，隔离真实 HA 凭据与任意代码/网络能力；没有可验证边界时只使用脱敏静态资料。
2. 按官方格式创作本项目自己的 `SKILL.md`，只引用已核实工具，不复制上游技能或添加虚构接口。
3. 在独立测试 profile 中人工审查发现路径、名字冲突、内容扫描及实际加载结果；本次没有做这些操作。
4. 用离线样本测试正常、缺失、过期、不可用、恶意实体描述等场景，确认拒绝任何直接或间接写操作、不泄露秘密。
5. 经人工批准后，才验证隔离环境和真实 HA 的只读读取；记录上游 SHA、模型/配置、测试输入和结果。通过不意味着控制功能自动获准。

[docs]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/website/docs/user-guide/features/skills.md
[code]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/tools/skills_tool.py
