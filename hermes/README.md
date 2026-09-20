# 交小西 × Hermes Agent：集成研究与安全边界

> **状态：研究与规划，未部署，未连接或验证真实 Home Assistant（HA）。** 本目录只有项目自己的说明、策略草案和 Skills 规划，不包含 Hermes Agent 上游代码、安装包或可执行 HA 适配器。交小西项目与 NousResearch/hermes-agent 分离；上游应在独立目录/运行环境安装和维护，不复制进本仓库。

## 1. 核查基线

- 官方仓库：<https://github.com/NousResearch/hermes-agent>。
- 本次观察到的 `main` commit：[`f9524d3f119c672e4a4444f56d582e7475716ba3`](https://github.com/NousResearch/hermes-agent/commit/f9524d3f119c672e4a4444f56d582e7475716ba3)。官方提交 Feed 标注时间为 `2026-09-20T03:03:15Z`。
- 优先请求 [GitHub API](https://api.github.com/repos/NousResearch/hermes-agent/commits/main)，但返回 HTTP 403（匿名 rate limit）。随后从[官方 Atom Feed](https://github.com/NousResearch/hermes-agent/commits/main.atom)取得 SHA，再读取该 **SHA 固定的 raw 源码与文档**。这不是对未来 `main` 的承诺，也不是本地安装版本证明。
- 下文以固定版本的实现为准；没有执行上游安装、CLI、单元测试或真实 HA 请求。

## 2. 已核实的原生 HA 工具

依据 [HA 工具源码][ha]，toolset 名称是 **`homeassistant`**，一次包含以下四个工具；它不是一个只读工具集。

| 工具名称 | schema 参数 | 实际 REST 行为 |
| --- | --- | --- |
| `ha_list_entities` | 可选 `domain: string`、`area: string` | `GET /api/states` 后在客户端筛选，返回数量、实体 ID、状态、友好名称 |
| `ha_get_state` | 必需 `entity_id: string` | `GET /api/states/{entity_id}`，返回状态、attributes、last_changed、last_updated |
| `ha_list_services` | 可选 `domain: string` | `GET /api/services`，返回域、服务描述及字段描述摘要 |
| `ha_call_service` | 必需 `domain: string`、`service: string`；可选 `entity_id: string`、`data: string` | `POST /api/services/{domain}/{service}`；`data` 是 **JSON 字符串**，不是 schema 中的 object |

注意实现细节：

- `area` 只是对 `attributes.friendly_name` 或 `attributes.area` 的不区分大小写子串匹配，**不是 HA area registry 查询，更不是房间权限边界**；即使筛选一个域/房间，列表工具仍先读取全部 `/api/states`。
- 服务调用 handler 将字符串 `data` 解码为 JSON；内部 helper 也能接收字典，但不能因此把公开 schema 写成 object。顶层 `entity_id` 若非空，会覆盖 `data` 中同名字段；顶层目标可省略，`data` 内容没有实体白名单检查。
- `ha_list_services` 的结果是压缩后的描述，不等于完整参数校验 schema，也不代表某服务已获本项目授权。
- 成功结果外层包在 `result` 中；服务调用返回的 `success: true` 及 `affected_entities` 来自 HTTP 响应解析，**不证明真实设备已经达到目标状态**。
- 这四个 REST 工具不等于摄像头识别、历史趋势分析、实时事件订阅或自动化系统。本项目尚未实现这些能力，也没有部署上游 HA 消息网关。

### 鉴权与配置位置

- `HASS_TOKEN`：HA **Long-Lived Access Token**；HTTP 使用 `Authorization: Bearer …`。可用性检查只是 token 非空，不会验证网络、token 权限或 HA 可达性。
- `HASS_URL`：HA 基础 URL；默认 `http://homeassistant.local:8123`，实现去掉结尾 `/`。这不是已发现的本地地址；生产环境需要自行核查受信网络/TLS。
- [secret_scope 源码][secrets]：凭据通过 `get_secret` 按活动 profile 读取；普通单 profile 可回退进程环境，多 profile multiplex 不允许借用其他 profile 的环境凭据。
- [官方配置文档][config]：通常在活动 `HERMES_HOME` 下的 `.env` 存秘密、`config.yaml` 存配置（默认 home 为 `~/.hermes`）。不要把 token 写进本仓库、对话、技能、截图或命令行历史；此处不提供真实/示例 token。

## 3. 控制限制：真实粒度，而非安全承诺

### 上游已有的限制

[HA handler][ha] 对域/服务名及顶层实体 ID 做格式检查，并硬编码拒绝这些**服务域**：

`command_line`、`hassio`、`pyscript`、`python_script`、`rest_command`、`shell_command`。

这是域级拒绝列表，**不是“只允许交小西灯光/空调”的白名单**。本次核查的原生 HA handler 没有可配置的实体白名单、服务白名单、参数范围、逐次人工确认、占用状态联锁或 HA 专用只读环境变量。未在这些文件中发现的配置项不能编造成上游接口。

未被此拒绝列表覆盖的域可能仍有物理风险；例如脚本、场景或通用服务可间接触发多设备动作。因此不能把“非六个禁用域”解释为安全。HA 用户权限、反向代理策略及实际安装的服务还需独立审计；普通 token 不能假定天然只读。

### 上游配置能做到什么

- [toolsets.py][toolsets] 把四个 HA 工具分在同一个 `homeassistant` toolset 中。[`hermes tools` 的实现][tools-config] 是按平台启用/停用工具集，不是 HA 实体级权限编辑器。
- 新安装选择界面默认不预选 HA，但在没有显式平台清单的解析路径中，存在 `HASS_TOKEN` 会被视为 HA opt-in；CLI/cron/网关的实际工具清单必须核对，**不能依赖“默认没勾选”保证安全**。
- 已核实的全局停用配置是 `agent.disabled_toolsets`；[模型工具选择实现][model-tools] 在启用集合之后减去禁用集合。以下只是供独立 Hermes 实例人工合并审阅的片段，**本仓库没有应用它**：

```yaml
# 停用整个原生 HA 工具集：读和写都会停用；不是只读模式。
agent:
  disabled_toolsets:
    - homeassistant
```

已有禁用列表应保留、合并，不能直接覆盖。`hermes tools` 后续显式重新启用工具集会协调修改此列表，升级/配置变更后需要重新检查。

上述选择机制不是 HA 服务器侧访问控制。即使隐藏 HA 工具，能读取凭据并访问网络的 terminal、代码执行、浏览器、MCP/插件或子代理仍可能提供其他访问路径；必须以独立进程权限、秘密隔离和网络边界补齐。

### 交小西的默认安全状态

**设计默认只读；当前连只读运行链路也未部署。** 在真正的只读执行边界落地前，不向 Agent 提供真实 HA token，不启动原生 HA 控制工具集；需要演示时仅使用人工脱敏的静态状态资料，并标注为示例而非实时数据。

| 本地能力 | 状态 | 验收要求 |
| --- | --- | --- |
| 查询与建议、状态来源标注 | Planned | 只暴露审核过的读接口，证明不能通过替代工具进行写操作 |
| 实体/服务/参数白名单 | Planned | 独立执行层 fail-closed；校验所有目标来源，禁止省略目标扩大作用范围及间接绕过 |
| 有限控制与人工确认 | Planned | 先 dry-run 计划，再对精确目标与参数授权；过期/状态变化后重新确认 |
| 速率限制、审计、幂等和结果回读 | Planned | 脱敏记录，失败不盲重试，设备状态可核实，人工停机可用 |

策略文本见 [xiaoxi-policy.md](prompts/xiaoxi-policy.md)。**提示词和 Skill 只是行为指导，不是可执行访问控制**。本次不提供可直接复制的设备写操作、开锁/电源/脚本调用或未经隔离的 HA 启动示例。

## 4. CLI 与策略/Skill 的实际机制

按 [CLI parser][parser] 与[官方 CLI 文档][cli-doc]：

- `hermes` / `hermes chat` 启动 Agent 对话；`hermes tools` 打开配置界面，`hermes tools --summary` 显示当前配置摘要。
- `hermes chat --toolsets` 接受逗号分隔的 **toolset 名称**，不能把它写成细粒度 HA 授权开关。启用 `homeassistant` 会同时包含服务调用能力。
- `hermes chat -q` 在真实 TTY 中是交互会话的初始消息；`chat --oneshot`、`-Q` 或非 TTY 才是答完退出。不能把所有 `-q` 都描述为单次执行。
- `--skills` / `-s` 预加载已能发现的 Skill 名称，可重复/逗号分隔；聊天内 `/<skill-name>` 是加载技能指令，不是新注册的设备 API。
- 不使用 `--yolo`、`--ignore-user-config` 或 `--ignore-rules` 规避审阅/策略。`--safe-mode` 是排障模式，不是 HA 只读模式；顶层 `-z` 的 parser 还声明自动绕过审批，不适合本项目的控制安全方案。
- `prompts/xiaoxi-policy.md` **不会因文件名自动载入**，本次也没有接线。[官方 Context Files 文档][context] 说明受支持的项目上下文和 `HERMES_HOME/SOUL.md` 机制；未来由部署人员选择受支持入口，核实实际注入内容与工具边界。不要编造 `--policy-file` 之类参数。
- `hermes/skills/` 是本项目规划目录，不是 `.hermes/skills/`，不会仅因其存在就自动安装；详见 [Skills 规划](skills/README.md)。

## 5. 验证范围与下一步

已完成：固定 SHA 的官方源码/文档静态核查；人工比对工具名、参数、凭据名、过滤/禁用粒度及 CLI/Skills 机制。

未完成：安装 Hermes、执行 CLI 或上游测试、创建 HA 用户/token、连接真实 HA、发现真实实体、调用任何服务、测试网络/审批/物理设备。**没有依据声称“已部署”“已联调”“控制安全已验证”**。

后续应先在无真实设备的隔离环境验证只读边界，包括替代工具/嵌套目标/场景脚本绕过、无目标请求、注入文本、凭据泄漏、网络错误和配置重载；通过后再由操作者单独批准真实 HA 的只读接入。任何控制功能另行评审，不能仅凭自然语言确认启用。

## 官方来源索引（均固定为本次核查 SHA）

- [HA 工具实现][ha]：schemas、REST、鉴权和域级拒绝。
- [Toolset 定义][toolsets] / [工具配置实现][tools-config] / [工具选择与分发][model-tools]：工具集粒度及 token opt-in。
- [Profile 凭据解析][secrets] / [配置文档][config]：秘密与全局工具集禁用。
- [CLI parser][parser] / [CLI 文档][cli-doc]：真实参数及会话机制。
- [Skill 加载源码][skills-code] / [Skills 文档][skills-doc] / [上下文文档][context]：发现、加载和格式。

[ha]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/tools/homeassistant_tool.py
[toolsets]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/toolsets.py
[tools-config]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/hermes_cli/tools_config.py
[model-tools]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/model_tools.py
[secrets]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/agent/secret_scope.py
[config]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/website/docs/user-guide/configuration.md
[parser]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/hermes_cli/_parser.py
[cli-doc]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/website/docs/reference/cli-commands.md
[skills-code]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/tools/skills_tool.py
[skills-doc]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/website/docs/user-guide/features/skills.md
[context]: https://raw.githubusercontent.com/NousResearch/hermes-agent/f9524d3f119c672e4a4444f56d582e7475716ba3/website/docs/user-guide/features/context-files.md
