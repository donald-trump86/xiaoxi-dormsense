# XiaoXi DormSense 项目介绍 · 大纲 v1

## 制作约定

- 场景：本科课程项目规划介绍，不将规划写成已完成成果。
- 目标时长：10 分钟；页面建议讲述合计 8.9 分钟，预留 1.1 分钟缓冲。
- 视觉：风格 B「瑞士国际主义」；主题色为 IKB 克莱因蓝。
- 输出：单文件横向翻页网页 PPT，附本地 Motion One 兜底、演讲者模式和提词卡备注。
- IP：使用团队提供的 `xiaoxi-dormsense-logo.png` 作为项目 Logo；它不代表学校或相关虚拟形象官方授权，素材权利与课程展示范围仍由团队人工确认。
- 图片：封面使用项目 Logo；Hermes 证据页使用用户提供的 OpenRouter 月度榜单截图，并明确截图日期与动态快照属性。
- 真实性：当前项目是工程骨架与实施规划。UNO R4 WiFi 已确认；传感器型号、真实 MQTT/HA/Hermes 链路及实物控制均待验证。
- 隐私：声音测量只作为原始设想被说明；当前不采集、不保存声音或语音。若未来讨论环境声强，必须另行完成同住人同意与隐私评审。

## 叙事弧

1. Hook：城市天气预报无法代表具体宿舍微环境。
2. Context：个人智能音箱体验与两门课程内容汇合为项目方向。
3. Core：明确目标、主链架构、节点职责、边缘/主机分工与 Agent 角色。
4. Shift：从“会聊天”转向“状态有来源、能力有边界”的宿舍智能体。
5. Takeaway：诚实标注现状，并给出可执行的下一步扩展。

## 页面计划、版式与主题节奏

| 页码 | 页面 ID | 章节 | data-layout | 主题 | 页面目的 | 观众可见信息 | 演讲者补充 | 时长 | 转场 |
|---:|---|---|---|---|---|---|---|---:|---|
| 1 | cover | 开场 | SWISS-COVER-ASCII | accent | 建立项目名称与规划属性 | 项目 Logo；从宿舍微环境到可交互智能体 | 强调是课程项目规划，不是已完成产品 | 0.4 | 从名字进入真实问题 |
| 2 | forecast-gap | 问题 | S08 | light | 用二元对照解释需求 | 城市天气预报 vs 宿舍微环境 | 天气预报不是错，而是空间尺度不同 | 0.7 | 为什么我们会想到自己测 |
| 3 | project-origin | 动机 | S13 | dark | 说明方向如何形成 | 天气变化、智能音箱体验、课程方法三股动力 | 不把消费级音箱能力直接等同于本项目能力 | 0.7 | 把动机压成明确目标 |
| 4 | project-goals | 范围 | S19 | light | 定义规划能力与边界 | 温湿度、光照/状态、自然语言、隐私边界 | 声音不进入当前 MVP | 0.8 | 有目标后看数据怎样流动 |
| 5 | system-chain | 架构 | S11 | light | 呈现主链 | 环境→传感器→Arduino→MQTT→HA→Hermes | 分析旁路只读，控制只经 HA | 0.8 | 从链路回到节点角色 |
| 6 | node-roles | 架构 | S05 | dark | 解释三类节点/层级 | 测量、汇聚、控制三层 | 当前为有线传感器接 Arduino，Wi-Fi 是 Arduino 到 Broker | 0.8 | 为什么不让 Arduino 承担全部任务 |
| 7 | compute-boundary | 取舍 | S03 | light | 给出核心工程判断 | Arduino 专心采样，主机负责理解 | 边缘做确定性工作，不逐样本调用 LLM | 0.7 | 主机侧的智能由谁承担 |
| 8 | hermes-role | Agent | S04 | light | 解释选择 Hermes 的功能理由 | 自然语言、记忆、Skills、多模型、隔离、HA 集成 | 官方能力与权限风险同时说明 | 0.8 | 用公开使用数据补充选择依据 |
| 9 | hermes-ranking | Agent | S15 | light | 展示 Hermes 的月度公开使用数据 | OpenRouter 本月 #1；50.8T tokens；约为第二名 2.4 倍 | 强调是 2026-09-22 截图时点的动态快照 | 0.5 | 使用规模之后回到受控交互闭环 |
| 10 | interaction-loop | Agent | S14 | dark | 展示理想交互闭环 | 提问→读 HA→解释→建议→未来受控动作→状态回读 | 当前只读优先；控制仍是 Planned | 0.8 | 规划必须与现状分开 |
| 11 | current-status | 现状 | S08 | light | 诚实区分已有与待验证 | 已有工程骨架 vs 真实链路待验收 | 模拟/静态检查不能替代实物联调 | 0.7 | 接下来按阶段推进 |
| 12 | future-roadmap | 未来 | S16 | grey | 给出扩展方向 | TTS、真正无线、多物理量、历史分析、安全控制、多节点 | 先完成最小闭环，再扩展 | 0.7 | 用三条原则收束 |
| 13 | closing | 收束 | SWISS-CLOSING-ASCII | split | 留下可记忆结论 | 先感知、再理解、后控制 | 回扣开场问题并邀请讨论 | 0.5 | 结束 / Q&A |

## 事实与来源口径

- 项目状态、架构、安全与隐私边界：仓库 `README.md`、`docs/architecture.md`、`docs/roadmap.md`、`docs/experiments.md`、`hermes/README.md`。
- Hermes 官方定位与能力：<https://hermes-agent.nousresearch.com/>。
- Hermes 官方 Home Assistant 文档：<https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/homeassistant.md>。
- OpenRouter 月度排名：采用用户提供的 `openrouter-global-ranking-2026-09-22.jpg` 作为截图证据；只陈述截图中可见的 `This Month`、Hermes Agent `#1 / 50.8T tokens` 与第二名 `21.1T`，并明确排名会动态变化。
