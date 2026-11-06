# 开发协作与模块扩展指南

本文说明项目的日常开发工作流、分支与提交规范，以及如何向系统中新增一个传感器字段或智能体功能。

---

## 1. 分支与开发流程

项目采用清晰的功能分支开发模式：

1. **保持 `main` 分支稳定**：日常开发在功能分支（如 `feat/reproducible-baseline-and-day-history` 或按任务命名的 `feat/<topic>`、`fix/<topic>`）上进行。
2. **原子化功能提交**：每次提交聚焦一个独立的功能闭环（例如“新增固件纯逻辑头文件与 native 测试”、“更新桥接服务与单元测试”），方便回溯和代码研读（参见 [Git 提交学习索引](commit-guide.md)）。
3. **提交前本地自检**：
   ```bash
   source .venv/bin/activate
   python scripts/check_repository.py
   python -m unittest discover -s tests -p 'test_*.py' -v
   git diff --check
   ```

---

## 2. 如何扩展一个新的环境传感器字段？

由于系统采用**契约先行（Schema-First）与白名单网关**设计，若未来需要为 `node01` 增加新传感器（如 CO₂ 或气压），请按以下 5 步顺序同步修改：

1. **更新数据契约（[schemas/telemetry.schema.json](../schemas/telemetry.schema.json)）**
   - Schema 顶层设置了 `"additionalProperties": false`，需在 `properties` 与 `sensor_status.properties` 中添加新字段定义及合理数值上下界，并同步更新 [docs/mqtt-protocol.md](mqtt-protocol.md)。
2. **更新节点固件与 native 测试（[firmware/arduino-uno-r4/](../firmware/arduino-uno-r4/README.md)）**
   - 在 `include/` 下编写传感器帧解析或采样纯函数，在 `test/` 下补充边界测试并运行 `pio test -e native`。
3. **更新常驻验证器（[services/bridge/validator.py](../services/bridge/validator.py)）**
   - 在跨字段校验逻辑中注册新字段的单位、量程与 `sensor_status` 联动规则，并在 `services/bridge/tests/test_validator.py` 中添加正反例测试。
4. **更新 Home Assistant 实体与只读网关（[home-assistant/](../home-assistant/README.md) & [services/bridge/read_gateway.py](../services/bridge/read_gateway.py)）**
   - 在 `home-assistant/mqtt/node01-sensors.yaml` 中添加新 MQTT Sensor 模板（含 `expire_after: 35`）。
   - 若需允许交小西智能体读取该实体，将其 `entity_id` 加入 `read_gateway.py` 的白名单集合。
5. **更新历史滤波与智能体工作区说明（[analytics/](../analytics/README.md) & [hermes/workspace/AGENTS.md](../hermes/workspace/AGENTS.md)）**
   - 在 `analytics/src/environment.py` 中配置该通道的卡尔曼滤波过程噪声 $q$ 与测量噪声 $r$，并在 `AGENTS.md` 中告知智能体该实体的名称与物理含义。

---

## 3. 各模块单元测试速查表

| 模块路径 | 运行命令 | 说明 |
| --- | --- | --- |
| 仓库静态检查 | `python scripts/check_repository.py` | 校验全部 Markdown 本地链接、JSON Schema 与 YAML 语法 |
| 根目录集成测试 | `python -m unittest discover -s tests -p 'test_*.py' -v` | 校验遥测契约、模拟器、Compose 安全配置与 HA 24h 保留配置 |
| 安全桥接服务 | `python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v` | 校验 `validator`、`read_gateway`、`inference_egress` 与 `dashboard_ingress` |
| 历史统计与卡尔曼滤波 | `python -m unittest discover -s analytics/tests -p 'test_*.py' -v` | 校验 24h 滑动窗口统计、断流重置、夏令时边界与 SQLite 只读报表 |
| 红外学习与回放服务 | `python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v` | 校验 `learn1` 分包组装、14 字段前后比对、HTTP 接口与两阶段挑战码回放 |
| Hermes 红外插件 | `python -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v` | 校验插件工具参数校验、动作白名单与错误处理 |
| Hermes 天气插件 | `python -m unittest discover -s hermes/tests -p 'test_weather_plugin.py' -v` | 校验动态城市、指定城市、数据过期、边界与错误处理，全程使用模拟响应 |
| UNO R4 WiFi 固件 | `pio test -d firmware/arduino-uno-r4 -e native` | 在宿主机本地运行 SHT31 分帧、光敏归一化、点阵与按钮状态机测试 |
| ESP32-C3 红外固件 | `pio test -d firmware/esp32-c3-ir -e native` 及 `python -m unittest discover -s firmware/esp32-c3-ir/test -p 'test_*.py' -v` | 运行 C3 纯逻辑 native 测试与链接 `IRremoteESP8266` 源码的主机回归测试 |
| Hermes 完整补丁套件 | `python hermes/tests/run_offline.py` | 在无网络隔离容器中重放 17 文件补丁并执行 Python 与前端 AST 回归测试 |
