# 开发与协作流程

采用轻量 GitHub Flow：从 `main` 建短期分支 → 提交小步修改 → PR → 同伴审查与验证 → 合并 → 删除已合并分支。不要把本页中的示例命令理解为已执行，也不要把配置文件存在理解为组件已经部署。

## 1. 本地环境

Python 工具与测试统一使用 **Python 3.11+**。建议从仓库根目录创建独立环境：

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`。`requirements-dev.txt` 提供 `jsonschema>=4.23,<5`、用于严格日期校验的 `rfc3339-validator` 和 `PyYAML>=6.0.2,<7`；安装命令供开发者准备环境时使用，不表示仓库编写过程中已联网安装或已运行测试。

不要提交 `.venv`、设备口令、HA token 或含真实隐私的遥测。Arduino 固件的板卡工具链和平台部署分别依照 [硬件记录](hardware.md) 与 [部署说明](deployment.md)，Python 依赖安装不会部署 broker、HA 或 Hermes。

## 2. 任务与分支

先写 issue，至少包含：用户目标、负责人/审查人、输入与输出、影响路径、验收方法、依赖、隐私/硬件风险。按 [团队分工](team.md) 协调共享文件，尤其是协议、HA 配置与测试。

```bash
git switch main
git pull --ff-only
git switch -c feat/b-sensor-sampling
```

分支示例：

- `feat/a-mqtt-contract`：协议及兼容性测试。
- `feat/b-sensor-sampling`：UNO R4 WiFi 采样。
- `feat/c-ha-mqtt`：平台与 HA 映射。
- `feat/d-window-statistics`：只读分析与窗口统计。
- `feat/e-hermes-report`：报告与 HA 接口。
- `test/f-restart-scenarios`：重启、去重、恢复测试。
- `docs/experiment-template` 或 `fix/null-field-handling`：小范围文档或修复。

上述 Git 命令由成员按实际仓库状态自行执行，不要求脚手架创建者自动提交或推送。保持 PR 聚焦，避免混入不相关格式化或覆盖他人工作。

## 3. 基础验证（仓库根目录）

统一命令如下；必须记录实际运行结果，不可只写“应该通过”：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/check_repository.py
```

离线模拟冒烟检查：

```bash
python3 simulator/mqtt_node.py --count 3
```

模拟命令**默认只离线打印消息，不连接 broker、不控制 HA 或硬件**。检查消息应含 `schema_version="1.0"`、节点与启动身份、递增 `sequence` 和 `simulated=true`；无可靠 UTC 时 `timestamp=null`。温度、湿度和归一化光照可缺测为 `null`，光照不能写成 lux。

这些命令由仓库对应测试、检查脚本与模拟器提供；若当前分支缺少实现或依赖，应在 PR 标注阻塞并补齐，不能跳过后宣称通过。`unittest` 报告零测试不等于有效覆盖。基础检查也不验证实物接线、无线连接、HA 部署或 Hermes 可用性，相关验收必须另行执行并记录。

## 4. PR 与审查

建议 PR 正文：

```text
关联 issue / 负责人 / 审查人：
用户目标与本次变更：
影响目录、协议与兼容性：
数据来源：真实 / 模拟 / 人工 / 无数据
验证命令与实际结果（包含失败和未运行原因）：
实物/部署证据（没有则写未验证）：
隐私、权限、设备安全与回退方式：
AI 辅助情况（需要时链接到简要记录）：
已知限制和后续事项：
```

审查清单：

- 至少一名其他成员审查；变更协议时请消费者负责人确认，权限/控制变更请 C 及相关设备负责人复核。
- 测试覆盖正常、缺测、重复、乱序与重启；适用时核对 `(node_id, boot_id, sequence)` 去重。
- 分析只订阅约定的遥测镜像，控制只经 HA；没有未经授权的设备命令 topic 发布。
- 配置示例与真实配置分开；仓库中无密钥、住户信息和不必要的原始遥测。
- 命令输出与结论一致，未运行项写清原因；模拟通过不能改写成实测通过。
- 已提供 [轻量 CI](../.github/workflows/ci.yml)：检查文档/协议、离线测试和 Compose 结构；需提交推送后由 GitHub 执行，本地初始化不等于远程 CI 已通过。合并前仍应在 PR 粘贴本地结果；CI 不可用时由 reviewer 复核，不能声称已有远程成功记录。
- 有 reviewer 同意、必要验证完成且阻塞意见关闭后合并；分支保护是仓库管理员可选设置，不预设已启用。

## 5. GitHub Projects：手动即可

不要求 GitHub CLI、API token 或自动化机器人。可在网页手动创建一个 Project，使用 `Backlog / Ready / In progress / Review / Done` 五列；没有 Projects 权限时，用 issue labels 和一个置顶进度 issue 达到同样效果。

每张卡片关联一个 issue，手动填写负责人、阶段（Phase 1/2/3）、验收条件、依赖和目标日期。打开 PR 后移到 Review；合并且相应验收完成才移到 Done。代码已合并但实物尚未验证时，保留单独的“实物验收”任务，不能用 Done 掩盖待验证状态。

每次组会只更新实际变化：已完成证据、当前阻塞、下一步与负责人。参考 [路线图](roadmap.md) 而不是按虚构日程填写进度。

## 6. 接口变更与复现

- 先更新 [架构](architecture.md) / [MQTT 协议](mqtt-protocol.md)，补充合法及非法样例，再同步生产者、HA 映射和分析消费者。
- 协议字段或单位变化需明确兼容策略，不能悄悄复用旧含义；已运行设备的配置迁移和回退要写清楚。
- 固件、部署和分析实验记录代码版本、实际设备/组件版本、参数和去敏配置差异，参见 [实验方案](experiments.md)。
- 使用 AI 时遵循 [AI 使用规范](ai-usage.md)；代理与人工协作同样遵循 [AGENTS.md](../AGENTS.md)。
