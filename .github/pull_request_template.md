## 变更概述

- 简要说明本次 PR 解决的问题、新增的功能或重构的模块：
- 关联的 Issue 或课程任务阶段：

## 涉及模块

- [ ] `firmware/`（Arduino UNO R4 WiFi / ESP32-C3 固件与单元测试）
- [ ] `schemas/` 或 `docs/mqtt-protocol.md`（MQTT 协议与 JSON Schema 契约）
- [ ] `services/bridge/` 或 `services/ir_learning/`（安全桥接服务 / 红外学习服务）
- [ ] `home-assistant/` 或 `deploy/`（实体配置、保留策略、Docker Compose 编排）
- [ ] `analytics/`（滑动窗口统计与一维因果卡尔曼滤波）
- [ ] `hermes/`（语音/会话/品牌补丁、原生插件、工作区规则）
- [ ] `docs/` 或 `presentation/`（架构文档、实验说明、展示材料）

## 本地验证结果

请勾选或粘贴本次已执行的验证命令：

- [ ] `python scripts/check_repository.py`
- [ ] `python -m unittest discover -s tests -p 'test_*.py' -v`
- [ ] `python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v`
- [ ] `python -m unittest discover -s analytics/tests -p 'test_*.py' -v`
- [ ] `python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v`
- [ ] 子模块专项测试（如 `pio test -e native`、`hermes/tests/run_offline.py` 等）：

## 配置与兼容性检查

- [ ] 未包含任何真实密码、Token、私钥或个人敏感信息（均使用 `.example` 占位模板）
- [ ] 若修改了 Topic、Schema 或实体 ID，已同步更新关联的网关、验证器与文档
