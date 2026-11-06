# Git 提交历史学习与二次开发索引

本索引按**模块依赖顺序**整理 `feat/reproducible-baseline-and-day-history` 分支上的工程提交，便于小组成员与后续学习者逐步阅读代码。每个条目说明实现内容和源码入口，新增功能继续在对应模块的正式目录维护。

建议按照下表从上到下的顺序，结合 `git show <SHA>` 逐个模块研读：

---

## 1. 基础环境、硬件固件与安全桥接层（第 1–10 步）

| 序号 | 提交 SHA 与主题 | 核心设计思路与学习要点 | 关键文件入口 |
| --- | --- | --- | --- |
| 1 | [9c70f622c9](https://github.com/donald-trump86/xiaoxi-dormsense/commit/9c70f622c980cf37927be1e1a9bc67dc087f95c0) `chore(repo): ignore local runtime state and normalize Python dev requirements` | 统一本地 `.gitignore` 规则与开发依赖，隔离 `.env`、证书私钥、模型权重与私有运行目录。 | [.gitignore](../.gitignore)、[requirements-dev.txt](../requirements-dev.txt) |
| 2 | [0caaa384aa](https://github.com/donald-trump86/xiaoxi-dormsense/commit/0caaa384aa561ac354eb9b13a408f5a3ba5beee2) `test(ha): support split Home Assistant YAML includes in repository checks` | 扩展 YAML 检查器以支持 Home Assistant 的 `!include` 拆分语法，为多文件配置打好基础。 | [check_repository.py](../scripts/check_repository.py) |
| 3 | [0d063e0d61](https://github.com/donald-trump86/xiaoxi-dormsense/commit/0d063e0d61d563f957a2900eb37e01f3a60e2a89) `feat(firmware-uno): add UNO R4 WiFi sensing, LED companion, and button gesture headers` | 将 UNO 串口分帧、EEPROM 启动计数、12×8 点阵五幕动画与按钮状态机抽离为纯头文件，并编写 34 项 native 测试。 | [sht31_uart.h](../firmware/arduino-uno-r4/include/sht31_uart.h)、[led_companion.h](../firmware/arduino-uno-r4/include/led_companion.h)、[boot_state.h](../firmware/arduino-uno-r4/include/boot_state.h) |
| 4 | [e40fc2f48e](https://github.com/donald-trump86/xiaoxi-dormsense/commit/e40fc2f48ee728725a52bc96277cb4911d58f991) `feat(firmware-c3): add ESP32-C3 infrared receive and single-frame AC command firmware` | 建立 ESP32-C3 红外收发节点初始工程，分离命令校验纯逻辑头文件与硬件驱动。 | [ir_node_logic.h](../firmware/esp32-c3-ir/include/ir_node_logic.h)、[main.cpp](../firmware/esp32-c3-ir/src/main.cpp) |
| 5 | [b787696d54](https://github.com/donald-trump86/xiaoxi-dormsense/commit/b787696d54cf0d5ac995da8062a50d2ab9185950) `feat(bridge): add fail-closed node01 MQTT telemetry validator` | 在遥测进入 HA 前增加常驻验证器，强制执行 JSON Schema 校验与 `(boot_id, sequence)` 单调防重放。 | [validator.py](../services/bridge/validator.py)、[test_validator.py](../services/bridge/tests/test_validator.py) |
| 6 | [c696c4c63c](https://github.com/donald-trump86/xiaoxi-dormsense/commit/c696c4c63c8b208922f684fd4071cf0db5a43269) `feat(ha): add validated node01 and event sensor templates` | 定义温度、湿度、光照、按钮事件、红外事件五大 HA 实体及 35 秒断流自动过期规则。 | [node01.yaml](../home-assistant/mqtt/real/node01.yaml)、[events.yaml](../home-assistant/mqtt/real/events.yaml) |
| 7 | [d191167c21](https://github.com/donald-trump86/xiaoxi-dormsense/commit/d191167c21968dfac0deccfb3d99129f69af976b) `feat(bridge): add five-entity read-only Home Assistant gateway` | 封存 HA 后端高权限 Token，仅向智能体网段暴露 5 个白名单实体的只读 `GET` 接口。 | [read_gateway.py](../services/bridge/read_gateway.py)、[test_read_gateway.py](../services/bridge/tests/test_read_gateway.py) |
| 8 | [0485e6a41b](https://github.com/donald-trump86/xiaoxi-dormsense/commit/0485e6a41bd36826be2f46a72844ff8594fc6518) `feat(bridge): add allowlisted HTTPS CONNECT egress proxy` | 为处于 `internal` 隔离网段的智能体提供固定域名白名单的 HTTPS `CONNECT` 代理。 | [inference_egress.py](../services/bridge/inference_egress.py)、[test_inference_egress.py](../services/bridge/tests/test_inference_egress.py) |
| 9 | [073c8594ef](https://github.com/donald-trump86/xiaoxi-dormsense/commit/073c8594ef90910dd6a6e172711b0c4de96d7199) `feat(bridge): add loopback dashboard ingress forwarder` | 将宿主机 `127.0.0.1:9119` 流量转发至内部网段的 `hermes:9119`。 | [dashboard_ingress.py](../services/bridge/dashboard_ingress.py)、[test_dashboard_ingress.py](../services/bridge/tests/test_dashboard_ingress.py) |
| 10 | [be069f9d45](https://github.com/donald-trump86/xiaoxi-dormsense/commit/be069f9d45759b5c30bbda9d40900d8662a0ce9e) `build(runtime): package non-root Python runtime image for bridge services` | 构建以非特权用户 `10001:10001` 运行的桥接服务通用 Python 容器镜像。 | [Dockerfile](../deploy/images/runtime/Dockerfile) |

---

## 2. Hermes 语音补丁、一维卡尔曼滤波与安全编排（第 11–20 步）

| 序号 | 提交 SHA 与主题 | 核心设计思路与学习要点 | 关键文件入口 |
| --- | --- | --- | --- |
| 11 | [37cd3f9740](https://github.com/donald-trump86/xiaoxi-dormsense/commit/37cd3f9740984839de6788e1192f648e91068757) `build(hermes): pin hash-locked voice and Chinese conversion dependencies` | 锁定 `edge-tts`、`faster-whisper`、`ctranslate2` 与 `zhconv` 的 SHA-256 哈希依赖锁文件。 | [requirements-voice.lock](../hermes/requirements-voice.lock)、[check_voice_dependencies.py](../hermes/check_voice_dependencies.py) |
| 12 | [802c40eb91](https://github.com/donald-trump86/xiaoxi-dormsense/commit/802c40eb91779a66727f32bc8894db7bc90de399) `feat(hermes): add reproducible voice and web UI patch set with offline regressions` | 基于固定摘要上游镜像实现可验证的源码补丁加载器与语音交互补丁。 | [apply_patch.py](../hermes/apply_patch.py)、[hermes.patch](../hermes/patches/hermes.patch) |
| 13 | [aaeddf8326](https://github.com/donald-trump86/xiaoxi-dormsense/commit/aaeddf8326a7bc1eb377b4c0811e026e270bb6fc) `build(hermes): add reproducible Hermes image recipe and workspace persona` | 编写分阶段构建并重编译前端 `web_dist` 的 `hermes/Dockerfile` 及交小西工作区规则。 | [Dockerfile](../hermes/Dockerfile)、[AGENTS.md](../hermes/workspace/AGENTS.md) |
| 14 | [923730d680](https://github.com/donald-trump86/xiaoxi-dormsense/commit/923730d680296715b8c9d0a4d09fa5da1b83b5c4) `feat(hermes): pin Faster-Whisper base model manifest and offline verifier` | 固定 Faster-Whisper `base` 模型文件校验清单，支持只读挂载与离线核验。 | [whisper-base.manifest.json](../deploy/examples/whisper-base.manifest.json) |
| 15 | [0f86f87acf](https://github.com/donald-trump86/xiaoxi-dormsense/commit/0f86f87acfe8f7833b2dc30035e36c74836d3bc0) `feat(analytics): summarize valid day windows and estimate current sensor state` | 实现 24 小时有效样本去重、断流检测与一维随机游走因果卡尔曼滤波平滑估计。 | [environment.py](../analytics/src/environment.py)、[test_environment.py](../analytics/tests/test_environment.py) |
| 16 | [ef9d2a20ac](https://github.com/donald-trump86/xiaoxi-dormsense/commit/ef9d2a20ac293700e7e4dc573c4dc481dd4002db) `feat(analytics): add read-only Home Assistant recorder report CLI` | 通过 SQLite `mode=ro&immutable=1` 安全读取 HA 历史库并输出 JSON 统计与滤波报告。 | [recorder_report.py](../analytics/src/recorder_report.py)、[test_recorder_report.py](../analytics/tests/test_recorder_report.py) |
| 17 | [d501d7dc2e](https://github.com/donald-trump86/xiaoxi-dormsense/commit/d501d7dc2e81be7d8df5d2ac9ab97fd6fd997280) `feat(deploy): add 7-role security Compose baseline and 24-hour HA retention` | 整合双网段隔离的 Compose 安全栈与 HA 每 5 分钟自动清理 24h 前历史状态的自动化配置。 | [compose.secure.yaml](../deploy/compose.secure.yaml)、[environment-retention.yaml](../home-assistant/automations/environment-retention.yaml) |
| 18 | [a0e5684dbc](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a0e5684dbc745b79f81874957e50868b07b80197) `docs: align architecture, module guides, and capability boundaries with baseline` | 补齐各子模块架构、部署与卡尔曼滤波设计说明。 | [architecture.md](architecture.md)、[history-and-kalman.md](history-and-kalman.md) |
| 19 | [b58e087a48](https://github.com/donald-trump86/xiaoxi-dormsense/commit/b58e087a488345079df8822117f24f094c169990) `ci: check bridge, analytics, and formal deployment boundaries` | 在 GitHub Actions 中集成根测试、桥接测试、滤波测试与 Compose 配置语法检查。 | [ci.yml](../.github/workflows/ci.yml) |
| 20 | [a584bbb326](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a584bbb326bce6a7b456602126a381a1aee3a119) `docs(git): add fine-grained commit study guide` | 建立第一阶段 20 个提交的阅读导航表。 | [commit-guide.md](commit-guide.md) |

---

## 3. 红外波形学习（`learn1`）、日常单会话延续与交小西品牌定制（第 21–30 步）

| 序号 | 提交 SHA 与主题 | 核心设计思路与学习要点 | 关键文件入口 |
| --- | --- | --- | --- |
| 21 | [05d82db913](https://github.com/donald-trump86/xiaoxi-dormsense/commit/05d82db91314be54f2bf1988ca629e96b963d7f6) `feat(ir): add bounded raw pulse timing export and NEC timing analyzer` | 为 ESP32-C3 增加原始微秒脉冲分包导出（`ir_raw_timing.h`）与离线时序分析工具（`nec_timing.py`）。 | [ir_raw_timing.h](../firmware/esp32-c3-ir/include/ir_raw_timing.h)、[nec_timing.py](../firmware/esp32-c3-ir/tools/nec_timing.py) |
| 22 | [0f0b40119e](https://github.com/donald-trump86/xiaoxi-dormsense/commit/0f0b40119ee4a80ff86063b9636532c2f1585399) `feat(ir): upgrade ESP32-C3 to passive startup and learn1 waveform capture/replay` | 支持原装格力遥控器 280 边沿双段长帧采样（上限 300 项）、14 字段状态解码、发射期间暂停接收中断与挑战码单次回放。 | [ir_learning.h](../firmware/esp32-c3-ir/include/ir_learning.h)、[ir_learning_capture.h](../firmware/esp32-c3-ir/include/ir_learning_capture.h)、[main.cpp](../firmware/esp32-c3-ir/src/main.cpp) |
| 23 | [ae303b7acc](https://github.com/donald-trump86/xiaoxi-dormsense/commit/ae303b7acc1d187ef4350c4a0a4bd0743f0d1bb9) `feat(learning): add host IR learning session service, one-shot replay CLI, and Compose role` | 实现宿主机红外逐键学习状态机、前后状态防呆比对、HTTP 服务端、两阶段回放 CLI 与 `ir-learning` 容器编排。 | [model.py](../services/ir_learning/model.py)、[server.py](../services/ir_learning/server.py)、[replay.py](../services/ir_learning/replay.py)、[compose.ir-learning.yaml](../deploy/compose.ir-learning.yaml) |
| 24 | [13952c1e0a](https://github.com/donald-trump86/xiaoxi-dormsense/commit/13952c1e0a5a8c600ac85c75dc7398a88304457b) `feat(hermes): add native IR learning plugin and minimal daily assistant configuration` | 新增 Hermes 原生空调学习插件 `xiaoxi_ir_learning`，并提供精简冗余平台、关闭自动清理的日常配置模板。 | [__init__.py](../hermes/plugins/xiaoxi_ir_learning/__init__.py)、[config.dorm-assistant.yaml](../hermes/config.dorm-assistant.yaml) |
| 25 | [a85b2da9ed](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a85b2da9ede1e4a0c1b4721ecbd9b9ab709bd025) `feat(hermes): add daily session continuation, xiaoxi CLI skin, and unified project branding` | 扩展 Hermes 补丁至 16 个文件，支持网页日常单会话自动延续、终端 `xiaoxi` 皮肤与全套交小西品牌图标替换。 | [hermes.patch](../hermes/patches/hermes.patch)、[xiaoxi.yaml](../hermes/skins/xiaoxi.yaml)、[manifest.json](../hermes/branding/manifest.json) |
| 26 | [8227c7c3f6](https://github.com/donald-trump86/xiaoxi-dormsense/commit/8227c7c3f62f022b7d4298043eb81ff84ff20b15) `docs: document IR waveform learning, daily Hermes workflow, and unified branding` | 同步红外波形学习、日常单会话与统一品牌定制文档。 | [ac-onboarding.md](ac-onboarding.md)、[hermes-daily-use.md](hermes-daily-use.md) |
| 27 | [a422044744](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a42204474476047068f299b57f6c4914f8f4042b) `docs(git): append IR learning, daily session, and branding commits to study guide` | 将第 21–26 步提交补充至本索引。 | [commit-guide.md](commit-guide.md) |
| 28 | [7ac052ee6d](https://github.com/donald-trump86/xiaoxi-dormsense/commit/7ac052ee6d72b01db96e9bb8a438237d32bcd4ce) `docs(core): rewrite root, architecture, deployment, and protocol guides for clarity` | 重写根目录与 `docs/` 下全部核心架构、硬件、协议、部署与开发指南，去除防御性免责声明，突出技术实现与复现流程。 | [README.md](../README.md)、[AGENTS.md](../AGENTS.md)、[architecture.md](architecture.md) |
| 29 | [a1dd231c13](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a1dd231c13d568f990edcf40a5fe7d7f370250b9) `docs(modules): rewrite module READMEs, persona guides, and remove defensive phrasing` | 重写各子模块 README、Hermes 工作区规则与代码注释，统一为自然清晰的技术说明风格。 | [hermes/README.md](../hermes/README.md)、[firmware/esp32-c3-ir/README.md](../firmware/esp32-c3-ir/README.md)、[services/ir_learning/README.md](../services/ir_learning/README.md) |
| 30 | [efaf7dc869](https://github.com/donald-trump86/xiaoxi-dormsense/commit/efaf7dc869409fdcc3a1deb424834dc569ab3cfc) `docs(git): update commit study guide with documentation rewrite commits` | 将第 28–29 步文档与表述重写提交记录至本学习索引。 | [commit-guide.md](commit-guide.md) |

---

## 4. 正式固件入口、语音交互与动态城市天气（第 31–34 步）

| 序号 | 提交 SHA 与主题 | 核心设计思路与学习要点 | 关键文件入口 |
| --- | --- | --- | --- |
| 31 | [846308415b](https://github.com/donald-trump86/xiaoxi-dormsense/commit/846308415b59cdc48f52874b8e19b679d9105f1b) `fix(firmware): preserve long holds and publish voice release events` | 明确两块板的正式固件入口；长按期间保留按钮基线，松开后发出结束录音事件，并增加 5 项 native 回归测试。 | [固件入口](../firmware/README.md)、[led_companion.h](../firmware/arduino-uno-r4/include/led_companion.h)、[协议说明](mqtt-protocol.md) |
| 32 | [e284ea5e0d](https://github.com/donald-trump86/xiaoxi-dormsense/commit/e284ea5e0d4742f0207874d36e1e82bc2a00a59e) `feat(hermes): add push-to-talk, Chinese speech, and dynamic weather` | 处理松开即停止并转写发送、中文单位朗读与自然对话；天气查询每次动态识别城市，使用受限出口读取国内实况；同步像素横幅及真实音色标签。 | [精确补丁](../hermes/patches/hermes.patch)、[天气插件](../hermes/plugins/xiaoxi_weather/README.md)、[出口代理](../services/bridge/inference_egress.py) |
| 33 | [`a955845`](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a9558453ea342b7d80b084c6cac0a03ff6d10807) `docs: align formal firmware, speech, and weather guides` | 更新正式目录导航、依赖版本、测试入口、天气与语音用法，并补全第 31–32 步的实际提交号。 | [README](../README.md)、[工程基线](engineering-baseline.md)、[日常使用](hermes-daily-use.md) |
| 34 | 本次提交 `fix(hermes): interrupt speech on new chat input` | 把终端输入与语音提交接到现有停止播放逻辑，输入草稿、录音和转写期间抑制自动朗读；覆盖云端、系统朗读和迟到合成回调。 | [Hermes 说明](../hermes/README.md)、[播放回归](../hermes/tests/test_voice_playback.cjs) |

---

## 5. 常用 Git 研读命令

```bash
# 查看全部分支提交图谱
git log --oneline --decorate -n 30

# 查看某次功能提交的完整改动（例如第 22 步 C3 红外学习固件）
git show 0f0b40119e

# 对比两个模块阶段之间的差异
git diff 05d82db913..ae303b7acc
```
