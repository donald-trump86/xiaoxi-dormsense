# 交小西（Hermes Agent）定制镜像、语音与品牌模块（`hermes`）

本目录基于固定摘要的上游镜像 `nousresearch/hermes-agent@sha256:39c4ac5a8eaecddc525cd680eb4bda1143f2b12e8f21e2d63c2d5d471a8390c8`（v0.21.4），提供可复现的**语音交互、网页端日常单会话延续、空调红外逐键学习插件与交小西全套品牌界面**定制方案。

---

## 1. 目录结构与核心文件

| 路径 | 功能说明 |
| --- | --- |
| [Dockerfile](Dockerfile) | 可复现构建配方：校验上游镜像摘要与 Python 语音依赖锁文件，应用 16 文件源码补丁，复制品牌图标与终端皮肤，并重新执行 `tsc -b && vite build` 编译前端 `web_dist` |
| [apply_patch.py](apply_patch.py) / [patches/manifest.json](patches/manifest.json) | 严格源码补丁工具：校验 16 个目标文件修改前后的精确 SHA-256 摘要，应用 [patches/hermes.patch](patches/hermes.patch) 并复制交小西静态品牌资源 |
| [requirements-voice.lock](requirements-voice.lock) | 包含全部 35 个 wheel 包 `--hash=sha256:...` 的语音与简繁转换依赖锁文件（`edge-tts==7.2.7`、`faster-whisper==1.2.1`、`ctranslate2==4.7.1`、`zhconv==1.4.3`） |
| [check_voice_dependencies.py](check_voice_dependencies.py) | 校验语音依赖锁文件完整性与容器环境 `pip check` 兼容性的脚本 |
| [config.dorm-assistant.yaml](config.dorm-assistant.yaml) | 面向宿舍日常使用的精简配置模板（仅开启 `homeassistant`、`xiaoxi_ir_learning`、`memory`、`session_search`，关闭冗余平台与会话自动清理，默认使用 `xiaoxi` 皮肤） |
| [plugins/xiaoxi_ir_learning/](plugins/xiaoxi_ir_learning/README.md) | 原生红外逐键学习插件，提供 `xiaoxi_ac_initialize`、`xiaoxi_ac_learn_key`、`xiaoxi_ac_learning_status` 三个对话工具 |
| [skins/xiaoxi.yaml](skins/xiaoxi.yaml) | 终端命令行专属 `xiaoxi` 像素字横幅与配色皮肤模板 |
| [branding/](branding/README.md) | 网页端与浏览器标签页使用的交小西圆形徽标、登录页插画与 Favicon 资源 |
| [workspace/AGENTS.md](workspace/AGENTS.md) | 注入 `/opt/data/workspace/AGENTS.md` 的交小西日常运行准则与传感器/红外状态解读规范 |

---

## 2. 16 文件源码补丁（`patches/hermes.patch`）详解

补丁在不改动上游核心 Agent 推理循环的前提下，精准增强了以下四个子系统：

1. **本地 Whisper 语音转写与 Edge TTS 语音合成（4 个后端文件）**
   - `hermes_cli/web_routers/audio.py`：在 `/api/audio/transcribe` 中接入本地 Faster-Whisper 模型并用 `zhconv` 统一转换为简体中文；在 `/api/audio/speak` 中支持 7 种允许的中文 Edge TTS 声线（默认 `zh-CN-XiaoyiNeural`），通过请求级关键字参数 `edge_voice` 传递声线，避免多线程全局环境变量竞争。
   - `tools/tts_tool.py` 与 `tools/transcription_tools.py`：扩展请求级 `edge_voice` 参数与本地 Whisper 模型路径解析。
2. **网页侧边栏语音卡片与日常单会话自动延续（2 个核心前端页面）**
   - `web/src/components/ChatSidebar.tsx`：新增“小西语音交互”控制卡片，支持麦克风录音转写、自动播报开关、7 种中文声线选择与状态提示。
   - `web/src/pages/ChatPage.tsx`：
     - 监听 `eventsFeedClient` 的 `message.complete` 事件自动朗读助手最新回复，并通过 `latestCallbackRef` 与 `AbortController` 防止切页或连续消息时的旧音频串音。
     - 按 `[hermes.chat.last-session.v1, HERMES_BASE_PATH, profile]` 在浏览器 `localStorage` 中持久化当前会话的数据库 ID（`stored_session_id`），刷新或重开页面时自动通过 `getSessionLatestDescendant` 续接同一日常会话，同时完整保留点击 `New (empty)` 新建空白会话与点击历史记录切换会话的能力。
3. **全套交小西品牌界面与去除上游第三方标识（10 个 TUI / Web 品牌文件）**
   - `hermes_cli/banner.py`、`hermes_cli/skin_engine.py`、`ui-tui/src/banner.ts`、`ui-tui/src/components/branding.tsx`、`ui-tui/src/app/CommandStep.tsx`：将终端默认横幅与命令提示替换为 `xiaoxi · DormSense` 像素标识，移除上游 `Nous Research` 署名。
   - `web/index.html`、`web/src/App.tsx`、`web/src/components/Header.tsx`、`web/src/components/LoginGate.tsx`、`web/src/pages/StatusPage.tsx`：将网页标题、左上角导航栏、密码登录门禁页与状态页徽标统一替换为交小西项目图标。

---

## 3. 本地验证与镜像构建命令

```bash
source .venv/bin/activate

# 1. 运行补丁清单校验与红外学习插件单元测试
python -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v

# 2. 在无网络隔离容器中重放 16 文件补丁并执行全部 26 项 Python 测试 + 18 项前端 AST 回归测试
python hermes/tests/run_offline.py

# 3. 校验本地 Faster-Whisper base 模型目录（部署安全栈前执行）
python hermes/verify_whisper_model.py /path/to/faster-whisper-base

# 4. 构建定制后的 Hermes 容器镜像
docker build -f hermes/Dockerfile -t xiaoxi-dormsense/hermes:local hermes
```
