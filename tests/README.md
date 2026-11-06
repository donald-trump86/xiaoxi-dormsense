# 自动化测试体系说明（`tests`）

项目构建了覆盖**数据契约、跨模块配置、安全桥接、历史滤波、红外学习与智能体补丁**的分层自动化测试体系。

---

## 1. 根目录测试套件（`tests/`）

| 测试文件 | 覆盖内容 |
| --- | --- |
| [mqtt/test_protocol.py](mqtt/test_protocol.py) | 校验 [schemas/telemetry.schema.json](../schemas/telemetry.schema.json) 对合规样本、缺失字段、越界数值与 `sensor_status` 冲突的判定逻辑 |
| [simulation/test_node.py](simulation/test_node.py) | 校验 `simulator/mqtt_node.py` 生成的遥测帧结构、序号递增与缺测模拟参数 |
| [test_whisper_manifest.py](test_whisper_manifest.py) | 校验 Faster-Whisper `base` 模型文件清单与离线校验逻辑 |
| [integration/test_configuration.py](integration/test_configuration.py) | 校验 Home Assistant、Mosquitto 与 Compose 模板中的 Topic 及实体名称一致性 |
| [test_formal_baseline.py](test_formal_baseline.py) | 校验七角色安全栈 `deploy/compose.secure.yaml` 的双网段隔离、只读文件系统与非特权 UID 约束 |
| [test_environment_retention.py](test_environment_retention.py) | 校验 Home Assistant 24 小时滚动历史保留自动化配置与三实体作用域 |

---

## 2. 全仓测试一键运行清单

```bash
source .venv/bin/activate

# 1. 静态检查（Markdown 链接、JSON Schema、YAML 语法）
python scripts/check_repository.py

# 2. 根目录契约与配置测试（31 项）
python -m unittest discover -s tests -p 'test_*.py' -v

# 3. 安全桥接服务测试（190 项）
python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v

# 4. 24h 统计与一维因果卡尔曼滤波测试（23 项）
python -m unittest discover -s analytics/tests -p 'test_*.py' -v

# 5. 宿主机红外学习与挑战码回放测试（52 项）
python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v

# 6. ESP32-C3 固件主机测试（22 项）与 Hermes 插件测试（14 项）
python -m unittest discover -s firmware/esp32-c3-ir/test -p 'test_*.py' -v
python -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v

# 7. PlatformIO 固件 native 单元测试（UNO 39 项 + C3 13 项）
pio test -d firmware/arduino-uno-r4 -e native
pio test -d firmware/esp32-c3-ir -e native

# 8. Hermes 16 文件补丁与前端 AST 离线回归测试（需本地 Docker 含上游基础镜像）
python hermes/tests/run_offline.py
```
