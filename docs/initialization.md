# 项目工程初始化记录与验收报告

**项目名称**：XiaoXi DormSense（交小西宿舍智能体）  
**初始化基线**：GitHub 现有空仓库（仅包含 MIT `LICENSE`）  
**完成时间**：2026-03  
**状态**：初始化完成，待硬件与服务联调（Under Development）

---

## 1. 初始化完成情况概述

本项目作为西安交通大学本科《无线传感网络》与《大数据基础》六人课程设计，已完成第一阶段的工程骨架初始化与协作规范制定。

已完成的核心工作包括：
1. **保留既有资产**：确认保留根目录已有的 MIT `LICENSE`，未擅自修改或替换开源协议。
2. **上游 Hermes Agent 深度核查**：
   - 核查基线：NousResearch/hermes-agent 官方 Git Commit `f9524d3f119c672e4a4444f56d582e7475716ba3`。
   - 确认了原生 `homeassistant` 工具集（`ha_list_entities`、`ha_get_state`、`ha_list_services`、`ha_call_service`）与环境变量（`HASS_URL`、`HASS_TOKEN`）。
   - 明确了上游缺乏细粒度实体/服务白名单的事实，确立了**默认只读、执行层 Planned** 的安全防御架构。
3. **MQTT v1 通信契约与 Schema 冻结**：
   - 制定了 `docs/mqtt-protocol.md`。
   - 编写了标准的 Draft 2020-12 `schemas/telemetry.schema.json`。
   - 设计了基于 `(node_id, boot_id, sequence)` 的三元组去重主键，明确了断网/重启边界与时间戳规范（无 NTP 时必须为 `null`）。
4. **离线优先模拟器与示例配置**：
   - 实现了无外部依赖即可运行的离线模拟器 `simulator/mqtt_node.py`（默认仅离线输出 JSONL，数据显式标记 `simulated=true`）。
   - 提供了 Home Assistant 模拟传感器配置样例 `home-assistant/mqtt/sensors.yaml` 与看板样例。
   - 提供了本地隔离部署的 Docker Compose 模板 `deploy/compose.yaml`（仅绑定 127.0.0.1）。
5. **六人团队协作与课程实验规范**：
   - 制定了六人三组的职责分工与交付验收表（`docs/team.md`）。
   - 制定了涵盖两门课程 13 项实验的目的、方法与指标规范（`docs/experiments.md`）。
   - 制定了 GitHub Flow 流程、Issue 模板、PR 模板与 CI 流水线配置。
   - 制定了统一的 `AGENTS.md` 与 `docs/ai-usage.md`，严禁伪造实验数据与运行结论。

---

## 2. 离线验证与测试结果

在本地 Python 3.11+ 隔离环境（`.venv`）中执行了全部基础验证：

```bash
# 1. 仓库链接、Schema 与 YAML 语法检查
python scripts/check_repository.py
# PASS: local paths, schema/sample and YAML syntax checked

# 2. 单元与集成测试套件
python -m unittest discover -s tests -p 'test_*.py' -v
# Ran 17 tests:
# - MQTT 契约合法性及字段类型、时间格式、交叉一致性拒绝测试全部通过
# - 离线模拟器批次输出、随机种子复现性、启动 ID 唯一性与异常参数拦截测试全部通过
# - 静态集成配置一致性、端口安全绑定、非匿名 Broker 验证全部通过

# 3. Docker Compose 语法与结构静态核验
docker compose -f deploy/compose.yaml config --quiet
# 语法合规，未暴露公网端口

# 4. 离线模拟器烟测
python simulator/mqtt_node.py --count 3
# 正确生成包含 schema_version="1.0" 与 simulated=true 的 3 条结构化 JSONL 数据
```

---

## 3. 当前未验证与限制声明

为了遵循工程诚实与学术诚信原则，特此声明以下内容**尚未进行现场实测或部署验收**：
1. **实物硬件**：除确认拥有 Arduino UNO R4 WiFi 主板外，具体传感器型号、引脚分配及供电尚未实测。
2. **服务部署**：Docker 容器、Mosquitto Broker 与 Home Assistant 尚未在真实物理网络中启动运行。
3. **网络与通信**：未进行真实的 Wi-Fi 射频收发或校园网络端到端压力测试。
4. **Hermes Agent**：尚未配置真实的 Home Assistant 长期访问 Token，未开展 Agent 端到端调用。
5. **实验数据**：仓库中除 `data/samples/telemetry.simulated.json` 为人工构造的协议示例外，不存在任何实测数据。
