# 交小西 × Hermes Agent：正式构建基线与来源记录

截至 2026-11-05，项目已有实验部署，以及原生 HA 只读查询和语音接入的历史验收记录。本目录把已有项目改动整理成固定镜像上的完整补丁、构建配方、项目人格和离线测试。**这里的正式镜像尚未部署；本轮离线验证不代表真实浏览器、麦克风、音质或完整系统已重新验收。**

下文正式基线的原始核对只读取六个公开源码文件、指定依赖/模型元数据和脱敏构建输出；当时未修改运行服务。之后的逐键学习与原生配置更新另列于本节，旧的“未部署”等表述记录各自当时状态。

## 当前运行能力与记忆配置

实际运行实例已接入[逐键学习插件](plugins/xiaoxi_ir_learning/README.md)和[私有学习服务](../services/ir_learning/README.md)。C3 `learn1` 已完成唯一一次烧录并确认在线，真实模型已调用学习状态工具返回空闲；原装遥控器逐键实录、学习后回放与空调效果仍待验收。正式镜像与这套实验运行实例须分别验证。

[日常助手配置片段](config.dorm-assistant.yaml)通过官方配置写入函数合并到现有 profile：保留 `homeassistant`、`xiaoxi_ir_learning`，追加 `memory` 和 `session_search`；禁用 `a2a-platform`、`spotify` 及看板自动通知/调度，保留当前模型、Whisper/Edge 语音、记忆加载、后台整理和上下文压缩。未删除旧聊天、账号或任务。插件可能延迟呈现于 `tool_search`、`tool_describe`、`tool_call`，这些原生桥接仍需保留。

2026-11-05 的新原生进程与无工具集覆盖的真实模型查询均已通过。当前版本没有按单个 HA schema 关闭工具的原生配置；四个 HA schema 仍属一个工具集，实际查询/控制边界继续由固定实体只读网关执行，不能把隐藏工具或提示词当作授权。

同一会话保留连续上下文，旧内容可能被原生压缩整理成摘要；重要偏好由 `memory` 保存，旧事按需用 `session_search` 检索。当前内置记忆/用户档案限额仍为 2200/1375 字符，未扩大模型上下文或承诺无限逐字记忆。已设置 `sessions.auto_prune: false`，避免默认按 90 天不活跃删除已结束聊天；数据库会随使用增长，用户仍可主动管理历史。

## 网页日常会话

当前实验实例的网页已更新：按浏览器、部署路径与 profile 保存经后端确认的真实会话 ID，默认继续上次选择，同时保留显式历史选择和新建操作。空白草稿要在数据库记录存在后才保存；没有启用 TUI 的自动 MRU 恢复。首次使用建议新建一次日常会话，让新工具配置明确生效。操作步骤与记忆边界见[日常使用说明](../docs/hermes-daily-use.md)。

此改动保留在当前正式补丁中，并通过 9 项实际 ChatPage 回调的隔离测试；现有运行容器完整 `tsc -b`/Vite 构建通过，9119 返回的新资源 SHA-256 与构建一致。登录后的真实刷新/切换和语音体验尚未验收。下文首次正式镜像构建是较早基线的历史记录；包含本次会话改动的镜像须重新构建，不能沿用旧镜像的构建结论。

## 项目品牌与模板

当前终端只显示一行小写 `xiaoxi`，不再使用像素头像；原生模板及安装/恢复方法见[终端皮肤说明](skins/README.md)。经典 CLI 与 Ink TUI 的固定厂商标语、图标和模型旁公司后缀已移除，真实版本与会话信息保留。

网页展开/折叠侧栏、移动顶栏、页脚、页签和登录页统一使用项目名称与既有 Logo。可复用图片、favicon、来源与尺寸清单见[品牌资源模板](branding/README.md)。这次在原容器内完成 `tsc -b`/Vite 与独立 Ink 构建并发布，重载了 dashboard 后台使登录页模板生效；实际 HTTP 图像/脚本哈希和登录页标题、内嵌项目 PNG 已核对。登录后的浏览器视觉尚未人工验收。

[Dockerfile](Dockerfile)保留公共皮肤副本，并安装网页品牌图片、应用当前十六来源补丁后分别构建网页与终端。原有六份语音/会话补丁输出字节保持不变，新增十份只覆盖品牌呈现。包含这些新改动的完整正式镜像尚未重新构建；旧镜像记录保留为历史证据。部署时把皮肤复制到选定持久 profile，再使用 `hermes skin use xiaoxi`。

## 构建输入与补丁来源

基底固定为：

```text
nousresearch/hermes-agent@sha256:39c4ac5a8eaecddc525cd680eb4bda1143f2b12e8f21e2d63c2d5d471a8390c8
```

[Dockerfile](Dockerfile) 使用本目录作为构建上下文。[.dockerignore](.dockerignore) 默认排除所有文件，只放行构建脚本、直接依赖及完整哈希锁、补丁及清单、项目人格、终端皮肤和四份公共品牌图片；测试、临时源码、模型缓存和用户配置均不进入镜像。上游代码保留在镜像中，仓库只保存带原始上下文的统一补丁，不复制上游源码树。

[补丁清单](patches/manifest.json)记录十六个指定文件的原始 SHA-256、观察到的实验容器 SHA-256 和正式结果 SHA-256，并固定[补丁](patches/hermes.patch)自身的 SHA-256：原六份语音/会话输出保持原样，新增十份界面品牌改动。[应用脚本](apply_patch.py)在写入前核对完整允许列表、所有原始文件、补丁内容、精确上下文及全部结果。任一不符就拒绝，不使用模糊匹配，也不把应用脚本当作在线更新工具。

| 上游文件（相对 `/opt/hermes`） | 完整补丁包含的项目改动 |
| --- | --- |
| `hermes_cli/web_routers/audio.py` | 每请求声线选择、来源/声线回执与一致性检查、既有物理按钮事件读接口 |
| `tools/tts_tool.py` | 独立声线覆盖、显式 Edge 不跨提供商回退、实际引擎/声线回执、旧调用签名兼容 |
| `tools/tts_tool_providers.py` | 前后端一致的声线白名单与既有朗读文本清理 |
| `tools/transcription_local.py` | 保留 `zhconv` 简体转换，移除全局语义替换 |
| `web/src/components/ChatSidebar.tsx` | 既有录音/朗读/按钮交互；声线选择、错误可见、来源显示、请求取消及旧回调隔离 |
| `web/src/pages/ChatPage.tsx` | 既有语音文本接线；按浏览器/部署路径/profile 续用真实会话 ID，隔离异步恢复与显式新建/历史选择 |
| `hermes_cli/banner.py`、`hermes_cli/cli_render.py` | 原生字标、经典/紧凑模式的名称与真实版本，移除固定营销后缀 |
| `ui-tui/src/components/branding.tsx`、`theme.ts`、`app/useMainApp.ts`、`app/uiStore.ts` | 单行终端名称、空头像单栏、默认品牌与启动标题 |
| `web/src/App.tsx`、`web/src/components/SidebarFooter.tsx`、`web/index.html` | 网页移动/展开/折叠图标、名称、页脚、页签标题与图标类型 |
| `hermes_cli/dashboard_auth/login_page.py` | 登录与无提供方页面的项目图片和名称，认证函数保持原样 |

旧私有补丁只覆盖最近一轮修改，其中三个“原始 SHA”与本次固定镜像不同，不能直接作为完整基线。正式补丁重新从原始镜像生成。唯一有意偏离当前实验容器源码的是转写处理：移除 `是内→室内`、`焦大小溪/交大小溪→交大小西`、`小溪→小西` 的全局替换，避免擅自改写用户原话；简繁转换保留。

## 构建与离线验证

在仓库根目录执行：

```bash
python3 -B hermes/tests/run_offline.py
# 只运行前端回调及两份 TSX 的转译检查：
python3 -B hermes/tests/run_frontend_tests.py

# 构建配方；不会启动或替换现有容器：
docker build --file hermes/Dockerfile --tag xiaoxi/hermes:formal hermes
```

离线运行器要求本机已有上述固定镜像，使用 `--pull=never`。它创建临时、无网络、只读根文件系统、移除 capabilities 的非 root 容器，把十六份允许的原始源码复制到容器自己的临时文件系统，再应用正式补丁。SDK、网络请求、配置、音频与浏览器接口全部用测试替身；运行器不会 `exec` 生产容器。

本次实际执行 `python3 -B hermes/tests/run_offline.py`，结果为：

- 十六个原始文件校验、只检查模式、正式应用及全部结果 SHA-256 通过；七个 Python 模块编译通过。
- 26 个 Python 离线用例通过：12 个迁移的声线/路由回归、6 个补丁拒绝与无提前写入测试、2 个转写语义保留测试、6 个依赖冲突门禁测试。
- 9 个实际侧栏语音回调及 9 个实际 ChatPage 会话恢复回调测试通过；`ChatSidebar.tsx` 与 `ChatPage.tsx` 的 TypeScript 转译通过。会话测试覆盖恢复/后继 ID、显式选择、新建后的历史选择、异步切换、profile 隔离、404/临时错误、存储拒绝及首次消息后持久化；使用离线替身。

首次实际镜像构建已通过六文件 SHA 校验，随后默认依赖解析报错 `Because there is no version of ctranslate2==4.8.5`。进一步从官方 PyPI JSON 及固定基底的隔离容器核实：四个指定版本均已发布，`4.8.5` 有 Python 3.13／Linux ARM64 wheel，且符合 `faster-whisper 1.2.1` 的 `ctranslate2>=4.0,<5` 约束。清空解析进程环境、关闭配置发现并明确使用官方索引后，解析成功。默认解析为何失败尚未证实，没有读取运行环境或配置来推断原因。

修订配方按以下输入构建：

- [直接依赖](requirements-voice.txt) 保持 `edge-tts==7.3.1`、`faster-whisper==1.2.1`、`ctranslate2==4.8.5`、`zhconv==1.4.1`。
- [基底版本约束](requirements-voice-base.txt) 记录语音依赖图中已存在于原始镜像的 21 项兼容版本；只通过 `importlib.metadata` 查询这些包，没有导入应用或导出全局包清单。
- [完整哈希锁](requirements-voice.lock) 由同一基底中的 `uv 0.11.6` 对官方 `https://pypi.org/simple` 解析生成，共 35 项。目标为 Python 3.13／Linux ARM64，保留上述 21 项基底版本；它固定语音依赖图，其他上游软件仍由基底镜像摘要固定。
- 构建仅向 `uv` 传入固定的 `PATH`、`HOME`、`TMPDIR`、`LANG`，使用 `--no-config`、明确的官方索引及 `--require-hashes --no-deps` 安装锁中全部 35 项；不会同步或卸载无关基底包。完整传递依赖均已列入锁，不能把这里的 `--no-deps` 用于仅含四项的文件。
- 安装前后均在无网络构建步骤执行全局 `uv pip check`。[依赖检查脚本](check_voice_dependencies.py) 记录并严格比较下述唯一既有冲突，同时核对 MSAL/cryptography 版本未变；新增冲突、缺失诊断或无法识别的输出均使构建失败。
- 安装后还要核对锁中全部 35 项版本，并实际导入 `edge_tts`、`faster_whisper`、`ctranslate2`、`zhconv`。门禁不构造模型或处理音频。

后续构建已通过补丁应用和 35 项哈希安装，随后全局检查暴露一个原始镜像已有的问题：`msal 1.36.0` 要求 `cryptography>=2.5,<49`，但基底安装的是 `50.0.0`。已在原始摘要镜像的无网络、无挂载、非 root 临时容器中复核，同样只有这一项冲突；正式检查脚本的原始基线记录步骤也已实测通过。本次保留这两个无关上游包的版本。修订门禁通过仅表示既有冲突保持原样且没有新增冲突，镜像仍有这一项上游依赖问题。

[来源清单](dependency-provenance.json) 保存官方发布 URL、目标 wheel 文件名、上传时间和 SHA-256，以及实际解析参数和边界。四项官方记录分别为 [Edge TTS 7.3.1](https://pypi.org/pypi/edge-tts/7.3.1/json)、[faster-whisper 1.2.1](https://pypi.org/pypi/faster-whisper/1.2.1/json)、[CTranslate2 4.8.5](https://pypi.org/pypi/ctranslate2/4.8.5/json)、[zhconv 1.4.1](https://pypi.org/pypi/zhconv/1.4.1/json)。PyPI 元数据中的哈希不代表本次检查已经下载、安装或验收这些 wheel；实际构建仍须校验下载内容并通过导入门禁。

主任务随后使用修订配方成功构建 `xiaoxi/hermes:formal`：六文件校验与补丁应用通过；安装前后唯一既有冲突完全一致；35 项锁定版本及四个库的实际导入通过；完整 `tsc`／Vite 前端构建通过，用时 1.84 秒。依赖门禁和前端构建均禁用网络，前端只使用基底已有的 `node_modules`，未执行 `npm install`。这些是实际镜像构建证据，独立于前述 AST／回调离线测试。构建继承上游的 `USER`、`ENTRYPOINT` 和 `CMD`。镜像尚未部署，也未因此验收模型、浏览器、麦克风或主观音质。

## 人格与 Whisper 模型前置条件

[项目人格](workspace/AGENTS.md) 最初复制自获准的项目自有工作区文件，原正式化快照 SHA-256 为 `41a741fa41b55ffd38b8ba67899fabc8d725e5b1c83f5e0474987cf96da9343b`。后续按本轮授权加入逐键学习与会话/长期记忆规则，当前 SHA-256 为 `0b338663609c8f7abd26b099694f61c9240a8fce4a785d5878b62e77dd060515`，已按旧哈希保护同步到实际工作区。行为规则仍须由只读网关、MQTT ACL、网络和工具权限执行。镜像中保留副本于 `/opt/xiaoxi/workspace/AGENTS.md`，部署任务须通过已核查的 Hermes 工作区上下文机制挂载/加载它；复制进镜像不代表已自动加载。[旧策略草案](prompts/xiaoxi-policy.md) 和 [Skills 规划](skills/README.md) 继续作为独立研究材料。

**正式部署前必须准备并核对本地 Whisper 模型目录，再只读挂载到 `/opt/data/whisper-base`。** [模型清单](../deploy/examples/whisper-base.manifest.json) 已按官方仓库元数据固定 `Systran/faster-whisper-base` 的 revision `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`，列出四个必需文件的大小：权重使用公开 LFS SHA-256，其余三个文件保留官方 Git blob SHA-1；没有把 Git blob 哈希改写成未经核实的 SHA-256。

部署人员独立准备文件后，从仓库根目录运行[离线校验器](../scripts/verify_whisper_model.py)：

```bash
python3 -B scripts/verify_whisper_model.py deploy/runtime/secure/whisper-base
```

该校验器只核对本地文件字节，不下载、加载模型或证明转写效果。公开 revision 和哈希不证明原私有模型目录与之匹配；本轮未读取、复制或验收现有模型权重。正式 Compose 的专用只读模型挂载要求目录预先存在，镜像构建保持无模型。模型未备齐或校验失败时，语音部署条件尚未满足。现有上游加载函数仍可能在缓存缺失时尝试下载，须继续由部署配置和出口权限约束，不能以临时开放新域名替代模型准备。

当前正式化工作没有新增设备控制、历史统计接口、自定义 Skill 或出口域名。历史原生查询和语音验收记录不能代替新镜像的构建、加载人格、模型挂载及真实交互验收；是否更新运行实例由单独的部署授权决定。

## 历史源码研究（2026-09-20）

以下保留固定上游 commit 的原始研究事实与来源。它与当前使用的镜像摘要是两个不同的版本锚点；不能据此推断镜像对应的 Git commit。涉及“本次”“当前”的旧研究表述只适用于当时核查范围。

### 1. 核查基线

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
