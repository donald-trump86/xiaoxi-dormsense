# 提交历史学习索引

这些提交于 2026-11-05 按模块和依赖整理已有工作，随后加入本导航。它们是真实的本次提交顺序，不是对过去开发日期或团队贡献的重建。

保留先前编辑及旧英文 README 的删除；凭据、私有实验、真实遥测、数据库、模型和音频留在本地忽略范围。临时智能体执行计划也留在私有目录。

## 阅读顺序

| 顺序 | 提交 | 学习重点 | 代表路径 |
| --- | --- | --- | --- |
| 1 | [2eec534c9e](https://github.com/donald-trump86/xiaoxi-dormsense/commit/2eec534c9e330d57117366e8dfb73be2e5de4a4e) `chore(repo): keep private experiments and local artifacts out of Git` | 保留已有忽略规则增量，将私有实验、运行状态和本地工具产物留在工作站。 | [.gitignore](../.gitignore) |
| 2 | [a63e0b70ac](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a63e0b70acefacc18f16864df518f09bece9ee4e) `fix(checks): parse supported Home Assistant includes without opening files` | 静态检查仅承认已使用的两个 include 标签，不执行引用或放开任意 YAML 标签。 | [check_repository.py](../scripts/check_repository.py) |
| 3 | [09e12263a9](https://github.com/donald-trump86/xiaoxi-dormsense/commit/09e12263a9c2ff5ad4737174a5bdfa44db0792fe) `feat(uno): add UART sensing and companion feedback firmware` | 迁入同一板卡的完整可构建基线，保留 UART、光照、TLS 预算、矩阵/按钮和已验证的寄存器修复。 | [main.cpp](../firmware/arduino-uno-r4/src/main.cpp)、[README.md](../firmware/arduino-uno-r4/README.md) |
| 4 | [7f3e0351ba](https://github.com/donald-trump86/xiaoxi-dormsense/commit/7f3e0351ba04e41488e26b0487e3f1fba369b5ca) `feat(ir): add ESP32-C3 receive and single-protocol send firmware` | 以已验证源码保留接收、无发射预览和单协议发送，明确启动发射、解析及 TTL 的既有限制。 | [main.cpp](../firmware/esp32-c3-ir/src/main.cpp)、[test_ac_handler.py](../firmware/esp32-c3-ir/test/test_ac_handler.py) |
| 5 | [e42e7d3898](https://github.com/donald-trump86/xiaoxi-dormsense/commit/e42e7d389878c70b54e881e559194468ca55da3a) `feat(validator): validate telemetry and persist replay watermarks` | 将 Schema、握手期限和防重放作为确定性转发边界；持久水位不是遥测归档。 | [test_validator.py](../services/bridge/tests/test_validator.py)、[validator.py](../services/bridge/validator.py) |
| 6 | [ecde52fc40](https://github.com/donald-trump86/xiaoxi-dormsense/commit/ecde52fc40a1fabd641d01d5f0b748067afce946) `feat(ha): define real sensor and event entities without changing fixtures` | 增加真实 node01 与 node02 映射及契约测试；保留 node90 模拟模板原始字节，环境实体不积累长期汇总。 | [test_ha_config.py](../services/bridge/tests/test_ha_config.py)、[events.yaml](../home-assistant/mqtt/real/events.yaml) |
| 7 | [3b14fdffbe](https://github.com/donald-trump86/xiaoxi-dormsense/commit/3b14fdffbec2fe5e8fba4be5201d920e84e6dc6b) `feat(gateway): expose authenticated fixed-entity HA reads` | 查询只取配置实体并投影字段；不可用事件清空旧内容，列表不读取后端全量状态。 | [read_gateway.py](../services/bridge/read_gateway.py)、[test_gateway_http.py](../services/bridge/tests/test_gateway_http.py) |
| 8 | [62b1ecad99](https://github.com/donald-trump86/xiaoxi-dormsense/commit/62b1ecad99ca6f2db1df60d3a86525ee314f8f6b) `feat(egress): restrict inference traffic to fixed HTTPS destinations` | 固定域名与端口的 CONNECT 代理拒绝非公网解析，不解密上游 TLS。 | [inference_egress.py](../services/bridge/inference_egress.py)、[test_inference_egress.py](../services/bridge/tests/test_inference_egress.py) |
| 9 | [7cc7d621c4](https://github.com/donald-trump86/xiaoxi-dormsense/commit/7cc7d621c4fbf8bbcd45a9ac56d8316d3df05798) `feat(ingress): forward dashboard traffic to the fixed Hermes service` | 恢复内部隔离网络的固定 Dashboard 入口，并在所有模块/测试齐备后记录源码哈希。 | [dashboard_ingress.py](../services/bridge/dashboard_ingress.py)、[test_dashboard_ingress.py](../services/bridge/tests/test_dashboard_ingress.py) |
| 10 | [e77bb0e533](https://github.com/donald-trump86/xiaoxi-dormsense/commit/e77bb0e5333cd95e24c043d00bf0b54ad601874d) `build(runtime): package bridge services with an explicit source allowlist` | 默认拒绝 Docker 上下文，仅包含四服务及契约依赖；以非 root 和独立水位目录运行。 | [.dockerignore](../.dockerignore)、[Dockerfile](../deploy/images/runtime/Dockerfile) |
| 11 | [044a817e22](https://github.com/donald-trump86/xiaoxi-dormsense/commit/044a817e222094c5c013f614d1247405e51a6b3f) `build(hermes): pin the voice graph and check the upstream dependency baseline` | 以完整哈希锁固定语音依赖；原有 MSAL 冲突须严格前后相同，新增冲突使构建失败。 | [check_voice_dependencies.py](../hermes/check_voice_dependencies.py)、[test_dependency_baseline.py](../hermes/tests/test_dependency_baseline.py) |
| 12 | [2c5f618601](https://github.com/donald-trump86/xiaoxi-dormsense/commit/2c5f618601a423feb6540f59cc5a5a3a878644be) `feat(hermes): preserve guarded voice and dashboard changes as a complete patch` | 完整六文件补丁、原始/结果哈希与回归一起保存；请求级声线隔离、取消和繁简转换不改写用户词义。 对唯一统一补丁数据文件放开必需的上下文空行空格检查，其他文件检查不变。 | [apply_patch.py](../hermes/apply_patch.py)、[run_frontend_tests.py](../hermes/tests/run_frontend_tests.py) |
| 13 | [8953938c58](https://github.com/donald-trump86/xiaoxi-dormsense/commit/8953938c58bc339601b2abfedc4e5dfd6cb8b4bf) `build(hermes): assemble the pinned image and project workspace persona` | 在完整补丁和依赖门禁后重建前端；保留上游启动方式，模型与实际人格加载仍有部署前提。 | [.dockerignore](../hermes/.dockerignore)、[Dockerfile](../hermes/Dockerfile) |
| 14 | [b642029d9d](https://github.com/donald-trump86/xiaoxi-dormsense/commit/b642029d9dabecff02cad716fc21c2075e2093b8) `feat(models): verify provisioned Whisper files against pinned metadata` | 校验固定 revision、文件大小和公开哈希；不下载模型、不读取真实配置或执行推理。 | [verify_whisper_model.py](../scripts/verify_whisper_model.py)、[test_whisper_manifest.py](../tests/test_whisper_manifest.py) |
| 15 | [0f86f87acf](https://github.com/donald-trump86/xiaoxi-dormsense/commit/0f86f87acfe8f7833b2dc30035e36c74836d3bc0) `feat(analytics): summarize valid day windows and estimate current sensor state` | 纯函数检查真实元数据、去重、重启与间断，并计算一维卡尔曼当前估计；参数未标定，不声称趋势预测。 | [environment.py](../analytics/src/environment.py)、[test_environment.py](../analytics/tests/test_environment.py) |
| 16 | [ef9d2a20ac](https://github.com/donald-trump86/xiaoxi-dormsense/commit/ef9d2a20ac2920b769b64d89a86af97118cb8ccf) `feat(history): read bounded recorder snapshots through a read-only CLI` | 只读查询三个固定实体和 86400 秒窗口，限制行数/耗时并投影属性；合成 SQLite 测试覆盖夏令时边界。 | [recorder_report.py](../analytics/src/recorder_report.py)、[test_recorder_report.py](../analytics/tests/test_recorder_report.py) |
| 17 | [d501d7dc2e](https://github.com/donald-trump86/xiaoxi-dormsense/commit/d501d7dc2e819d141f0d4b7f1004e80376975bfd) `feat(deploy): define the isolated stack and scoped day-retention automation` | 把七角色网络、假配置、TLS/ACL 示例和三实体 HA 周期保留作为可审查整体；不迁移现有服务。 | [test_environment_retention.py](../tests/test_environment_retention.py)、[test_formal_baseline.py](../tests/test_formal_baseline.py) |
| 18 | [a0e5684dbc](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a0e5684dbc74f5e5cdb0a035c14422fcad19bf93) `docs: reconcile deployment evidence, hardware limits, and onboarding plans` | 文档区分真实部署、离线验证和未来方案；保留先前 README_EN 删除，不伪造实物结果或过去提交。 | [README.md](../README.md)、[README.md](../analytics/README.md) |
| 19 | [b58e087a48](https://github.com/donald-trump86/xiaoxi-dormsense/commit/b58e087a488345079df8822117f24f094c169990) `ci: check bridge, analytics, and formal deployment boundaries` | 在所有源码和静态夹具齐备后启用 CI；功能分支单独 push 不声称已触发远程 Actions。 | [ci.yml](../.github/workflows/ci.yml) |
| 20 | [a584bbb326](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a584bbb326bce6a7b456602126a381a1aee3a119) `docs(git): index verified module commits for future study` | 建立首批 19 个功能提交的阅读顺序、代表路径与验证口径索引。 | [commit-guide.md](commit-guide.md)、[README.md](../README.md) |
| 21 | [05d82db913](https://github.com/donald-trump86/xiaoxi-dormsense/commit/05d82db9135cf2186e095bc85726cfcc54b58f2f) `feat(ir): add bounded raw pulse timing export and NEC timing analyzer` | 增加最多 300 项、每片 16 项的微秒脉冲分片格式化与 NEC 离线时序拼装诊断工具。 | [ir_raw_timing.h](../firmware/esp32-c3-ir/include/ir_raw_timing.h)、[nec_timing.py](../firmware/esp32-c3-ir/tools/nec_timing.py) |
| 22 | [0f0b40119e](https://github.com/donald-trump86/xiaoxi-dormsense/commit/0f0b40119e7c3ef43b49b004789cc8a83645921c) `feat(ir): upgrade ESP32-C3 to passive startup and learn1 waveform capture/replay` | 切换 C3 为被动静默启动，发射暂停接收中断，实现 `learn1` 波形采集、14 字段状态比对与一次性挑战码原始重放。 | [main.cpp](../firmware/esp32-c3-ir/src/main.cpp)、[ir_learning.h](../firmware/esp32-c3-ir/include/ir_learning.h) |
| 23 | [ae303b7acc](https://github.com/donald-trump86/xiaoxi-dormsense/commit/ae303b7accc4786416c9fc3248292b2bc016f51b) `feat(learning): add host IR learning session service, one-shot replay CLI, and Compose role` | 实现宿主机红外学习状态机、TLS 收集器、固定六动作 HTTP 服务、38kHz 标称载波门禁单次重放 CLI 与独立容器编排。 | [model.py](../services/ir_learning/model.py)、[replay.py](../services/ir_learning/replay.py) |
| 24 | [13952c1e0a](https://github.com/donald-trump86/xiaoxi-dormsense/commit/13952c1e0a2f5b15bf1b6069a67d4ce1a25b78ea) `feat(hermes): add native IR learning plugin and minimal daily assistant configuration` | 注册三个只读/学习引导工具且不向模型暴露原始发射，精简无用平台适配器并更新工作区人格说明。 | [__init__.py](../hermes/plugins/xiaoxi_ir_learning/__init__.py)、[config.dorm-assistant.yaml](../hermes/config.dorm-assistant.yaml) |
| 25 | [a85b2da9ed](https://github.com/donald-trump86/xiaoxi-dormsense/commit/a85b2da9ed2962272e3a813d8fa0f8f0f9c29f85) `feat(hermes): add daily session continuation, xiaoxi CLI skin, and unified project branding` | 将受保护补丁扩展至 16 个源码文件，支持网页默认延续日常会话、终端极简 `xiaoxi` 皮肤与全套交小西品牌图标。 | [apply_patch.py](../hermes/apply_patch.py)、[xiaoxi.yaml](../hermes/skins/xiaoxi.yaml) |
| 26 | [8227c7c3f6](https://github.com/donald-trump86/xiaoxi-dormsense/commit/8227c7c3f683100fb57577667abfb789fb944181) `docs: document IR waveform learning, daily Hermes workflow, and unified branding` | 同步更新红外学习、MQTT 协议、日常使用指南、品牌模板说明与 AI 使用记录，严格区分已验证项与待人工验收项。 | [hermes-daily-use.md](hermes-daily-use.md)、[README.md](../services/ir_learning/README.md) |

本索引由最后的 `docs(git)` 导航提交加入；用下面的命令查看它及完整的实际历史。所有功能边界都以可审查的文件组提交，没有拆散哈希绑定补丁，也没有按行数制造提交。

## 常用查看方法

```bash
git log --reverse --oneline 4ef28be44888..HEAD
git show --stat <提交SHA>
git show <提交SHA> -- <文件路径>
git diff <提交SHA>^ <提交SHA> -- <文件路径>
git log --oneline -- analytics/src/environment.py
git log -1 -- docs/commit-guide.md
```

先看某一步的提交说明了解目的，再看测试和源文件。要研究特定版本，可另建独立 worktree，避免覆盖正在修改的工作区；旧版固件与配置也不能直接当成当前设备的安全部署包。

## 验证口径

- 每次提交前，先把暂存区树导出至本任务专用的 detached worktree；根测试和本地路径/YAML 检查通过后才创建提交。桥接及分析目录出现后，也运行对应的累计测试。提交说明记录该次快照实际执行的检查。
- Hermes 完整补丁就绪后，在固定原始镜像的一次性无网络 fixture 中重新运行 26 项 Python 与 9 项实际侧栏回调测试，不使用正在运行的 Hermes 实例。
- 最终功能树的根测试为 31、桥接 190、分析 23；两板 native、目标编译和正式镜像构建属于此前已记录的验证，本次不重复硬件操作，不把源码提交等同于新实例上线。
- 现有 CI 对 `main` 的 push 和 PR 触发；只推送功能分支不代表 Actions 已运行或通过。保留 main 供人工审查与合并，不强推、不改远端设置。
- 清理配置与分析读取的实际 HA 证据见[历史说明](history-and-kalman.md)，更早的工程构建记录见[工程基线](engineering-baseline.md)，现场未验收项仍保持原标签。

后续修复按“一个问题/功能 + 必要测试 + 对应说明”继续提交；提交消息解释为什么改和实际验证，避免把下一阶段的设想写成已实现。
