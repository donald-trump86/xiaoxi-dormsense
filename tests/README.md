# 验证范围

在根目录虚拟环境安装基础与桥接依赖，然后运行：

```bash
python -m pip install -r requirements-dev.txt -r services/bridge/requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v
python -m unittest discover -s analytics/tests -p 'test_*.py' -v
python scripts/check_repository.py
```

## 根目录测试

- `mqtt/`：Schema、UTC/null 时间、缺测、字段/Topic 一致性和非法值拒绝。
- `simulation/`：离线模拟 CLI、序列、启动 ID、可复现合成值、参数错误。
- `integration/`：旧版 HA/Compose/Mosquitto 的静态一致性，保留既有模拟基线。
- [正式基线测试](test_formal_baseline.py)：七角色网络/凭据位置、固定实体、配置挂载、持久状态与默认只读 ACL。
- [模型清单测试](test_whisper_manifest.py)：用微型合成文件检查大小、SHA-256 / Git blob SHA-1、路径与符号链接拒绝；不读取真实模型。
- [环境保留策略测试](test_environment_retention.py)：固定三个实体、一天保留、定时/启动触发、无长期统计声明及只读模板挂载，不执行实际删除。
- [检查脚本](../scripts/check_repository.py)：Markdown 相对链接、JSON、Schema/样例和 YAML 语法。HA `!include` / `!include_dir_merge_list` 只识别标记，不打开其目标；不验证完整 HA 配置语义、远程链接或页内锚点。

这些测试不启动服务、不连接真实设备，也不校验实际账号权限。CI 还执行两个 Compose 的 `config --quiet`，只做解析，不运行 `up`。

## 历史统计与估计

[分析测试](../analytics/tests/)包括 18 个纯函数案例与 5 个微型 SQLite 案例，检查窗口、元数据、单位、去重、间断、手算卡尔曼、只读数据库、投影、行数限制和夏令时前后仍为 86,400 秒。均为合成输入；实际 HA 原生加载、定时触发、目标范围清理和真实历史摘要另行验收，见[历史说明](../docs/history-and-kalman.md)。本轮根目录 31、桥接 190、分析 23 项离线测试通过。

## 桥接、Hermes 与固件

[桥接测试](../services/bridge/tests/) 使用假 MQTT 回调、假时钟和有界 loopback HTTP fixture，覆盖 validator、五实体网关、出口代理、固定 Dashboard 转发与 HA 静态模板。它们会创建本机临时测试监听器，不连接现有 Broker/HA，不使用生产 Token。镜像中的同组测试另在无外网、只读文件系统和非 root 条件下执行。

Hermes 的补丁、语音请求隔离和实际侧栏回调测试：

```bash
python3 hermes/tests/run_offline.py
```

该命令需要本地已有固定上游镜像；只启动一次性 Docker fixture，`--network=none`、只读、非 root，不接触运行中的 Hermes。它复制六个允许的公开源码文件到临时目录，应用补丁并测试；不加载模型、调用语音服务、采集麦克风或测试音箱。源码语法检查、完整前端构建和实际浏览器交互是不同验证。

固件命令见 [UNO](../firmware/arduino-uno-r4/README.md) 与 [C3](../firmware/esp32-c3-ir/README.md)。native 是合成输入，目标板构建也不执行烧录。IR handler 的“关机”用例只在主机测试后端运行。

2026-11-05 的实际执行结果和构建证据见[工程基线](../docs/engineering-baseline.md)。真实 MQTT、HA 加载、Hermes 当前查询、浏览器录放音、按钮手势、独立供电及空调响应须分别按[实验方案](../docs/experiments.md)和[部署指南](../docs/deployment.md)记录。未执行的项目保留“未验证”，不以离线测试结果替代。
