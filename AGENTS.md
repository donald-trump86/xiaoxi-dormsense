# AI Agent 开发约定

本文件适用于整个仓库。各工具不一定自动识别 AGENTS.md，成员应主动加载它和负责模块的 README；不能以工具未自动读取为由绕过约定。

## 项目与目标

XiaoXi DormSense（交小西宿舍智能体）是六人本科课程项目，结合无线传感网络与大数据基础。已确认 UNO R4 WiFi 及部分未明确型号传感器。工程初始化不等于功能完成，不假设 HA、Hermes、传感器驱动或 ESP32 已可用。

## 架构约束

- 主链 **Arduino → Wi-Fi/MQTT → Home Assistant → Hermes Agent**。
- 分析通过[架构文档](docs/architecture.md)约定的 Broker 只读遥测镜像获取数据，保存 received_at 和原始 payload；不能直接控制设备。
- Agent 查询当前状态走 HA；历史统计接口与自定义 Skill 尚 Planned，不编造 HTTP 路径、CLI、配置或工具签名。依赖上游行为先核查[Hermes 来源记录](hermes/README.md)，必要时重新核查版本。
- 不逐样本调用 LLM，采样、异常检测、时效性和拒绝逻辑由确定性程序负责。不为小项目随意引入重服务或跨模块耦合。
- 控制仅能通过经审查的 HA 安全路径；当前默认不启用。提示词、Skill 和上游有限危险域黑名单都不是细粒度权限边界。

## 代码与配置

Python 3.11+ 遵循 PEP 8，函数职责清晰；Arduino 使用模块化 C++，非阻塞采样和明确的失败状态。UTF-8，LF。配置与代码分离，不硬编码 Wi-Fi/MQTT 密码、Token 或 API Key，不记录秘密到日志或错误消息。

读已有文件后再改，保留许可证和他人工作。避免随意升级依赖、整体格式化无关文件、复制 Hermes 上游。传感器型号、供电、接线与板卡支持未知时先询问/记待确认，禁止猜测生成驱动。

## MQTT 契约

所有发送端、HA配置、分析与测试遵守 [docs/mqtt-protocol.md](docs/mqtt-protocol.md) 与 [Schema](schemas/telemetry.schema.json)。未经 A/B/C/D 讨论不要修改已评审的通信协议。接口变化必须同一个 PR 更新契约、示例、消费者与测试并说明兼容性。

时间未同步则 timestamp=null；缺测通道=null；使用 boot_id+sequence 分段去重；合成数据 simulated=true，不把归一化 light 当作 lux。

## 模块边界

优先只改[团队分工](docs/team.md)指定目录。不要未经请求重构其他成员正在开发的模块。确需公共接口变更先说明影响并请求对应负责人评审；同一文件多人编辑时先协调，禁止覆盖、重置或删除未提交成果。

## 测试与文档

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/check_repository.py
```

在虚拟环境执行。新功能提供单元、模拟、静态配置或明确的人工验收步骤。记录实际运行命令、结果与未覆盖范围；不能把语法/模拟测试通过表述为实物、网络或完整系统可用。依赖缺失/硬件不可达应报告，而不是编造结果。

接口、环境变量、目录或部署命令改变时同步更新 README 与相关 docs。Planned 明确标注；不使用“已完成”描述未经验收的功能。

## Git 与协作

遵守 [GitHub Flow](docs/development.md)：main 稳定，分支开发，小粒度 PR，说明模块、公共接口和测试，至少相关负责人审查。AI 不应未经明确授权 commit/push、改远程设置、建 Release 或批量 Issues；禁止 force push、泄露凭据与覆盖他人改动。人工合并，冲突先沟通。

## AI 使用、学术诚信与安全

绝不编造硬件测试结果、传感器数据、无线网络性能、实验结论、参考文献或实际运行截图。可生成清楚标注的模拟数据，只用于开发/方法验证，不能代替真实课程实验。不得去掉 simulated 标识，不把 AI 输出直接当作科学结论。

重要代码生成、架构或实验分析按 [AI 使用记录模板](docs/ai-usage.md)记工具、目的、生成内容、人工修改和验证；不必记录普通聊天。生成结果必须由提交者理解并承担责任，不伪造人工复核记录。

不提交真实宿舍成员信息、活动轨迹、访问 Token、SSH Key 或原始私密日志。不得将个人数据交给第三方 LLM；引用资源核实出处和许可证。本项目不是西安交通大学或相关虚拟形象官方项目，不擅用受保护形象素材。
