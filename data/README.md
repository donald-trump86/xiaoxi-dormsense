# 示例数据与回归测试夹具（`data`）

本目录存放用于 JSON Schema 契约校验、CI 静态检查与离线单元测试的轻量级合成样例数据（标记为 `simulated: true`）：

- [samples/telemetry.simulated.json](samples/telemetry.simulated.json)：符合 [schemas/telemetry.schema.json](../schemas/telemetry.schema.json) 的单帧标准遥测示例，由 `scripts/check_repository.py` 在每次静态检查时自动验证。
- [processed/README.md](processed/README.md)：预处理输出目录说明。

真实运行环境中的 Home Assistant SQLite 数据库存放在已列入 `.gitignore` 的 `deploy/runtime/home-assistant/` 目录中，由 [analytics/src/recorder_report.py](../analytics/src/recorder_report.py) 直接只读读取。
