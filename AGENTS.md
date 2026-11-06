# 仓库开发与协作规范（AGENTS.md）

本文档为参与 **XiaoXi DormSense（交小西宿舍智能体）** 开发、维护与代码学习的同学及 AI 编程助手提供统一的工程规范。

## 1. 项目结构与分层职责

系统按职责划分为四个解耦层级，修改代码时请保持边界清晰：

1. **硬件固件层（`firmware/`）**
   - [firmware/arduino-uno-r4/](firmware/arduino-uno-r4/README.md)：`node01` 环境感知与点阵陪伴节点（SHT31 UART 解析、LM393 光照归一化、三线按钮手势、12×8 LED 点阵动画）。
   - [firmware/esp32-c3-ir/](firmware/esp32-c3-ir/README.md)：`node02` 红外收发与学习节点（`learn1` 300 项原始微秒脉冲采集、14 字段状态解码、挑战码单次回放）。
   - 核心纯逻辑均抽离在 `include/*.h` 头文件中，便于在不连接开发板时通过 `pio test -e native` 或主机编译器直接运行单元测试。
2. **数据契约与桥接服务层（`schemas/`、`services/`）**
   - [schemas/telemetry.schema.json](schemas/telemetry.schema.json) 与 [docs/mqtt-protocol.md](docs/mqtt-protocol.md) 定义统一消息格式。
   - [services/bridge/](services/bridge/README.md) 包含 `validator.py`（遥测校验与防重放）、`read_gateway.py`（五实体只读网关）、`inference_egress.py`（HTTPS 域名白名单代理）与 `dashboard_ingress.py`（9119 入口转发）。
   - [services/ir_learning/](services/ir_learning/README.md) 管理空调遥控器逐键学习会话、前后状态防呆比对与本地受控回放。
3. **平台与数据分析层（`home-assistant/`、`analytics/`）**
   - [home-assistant/](home-assistant/README.md) 存放 MQTT 实体定义与 24 小时滚动历史清理自动化。
   - [analytics/](analytics/README.md) 提供 24 小时滑动窗口统计、一维因果卡尔曼滤波（`environment.py`）与 SQLite 只读报表工具（`recorder_report.py`）。
4. **智能体与界面定制层（`hermes/`）**
   - [hermes/](hermes/README.md) 基于固定摘要的 Hermes 镜像，通过 `patches/hermes.patch`、`plugins/xiaoxi_ir_learning/`、`skins/xiaoxi.yaml`、`branding/` 和 `workspace/AGENTS.md` 实现语音交互、日常单会话延续、红外学习工具与交小西品牌界面。

## 2. 配置、凭据与隐私规范

- **严禁提交真实凭据**：Wi-Fi 密码、MQTT 账号密码、TLS 私钥、Home Assistant Token（`HASS_TOKEN` / `HASS_BACKEND_TOKEN`）、红外学习 Token 与大模型 API Key 只能存放在已列入 `.gitignore` 的本地私有文件（如 `.env`、`include/secrets.h`、`deploy/runtime/`、`experiments-private/`）中。
- **公开模板使用占位符**：跟踪的示例配置统一放在 `.env.example`、`deploy/secure.env.example`、`deploy/examples/` 和 `include/secrets.example.h` 中。
- **区分模拟与实测数据**：模拟器（`simulator/mqtt_node.py`）与测试夹具统一使用 `simulated: true` 和测试节点编号（如 `node90`），实机节点使用 `node01` / `node02` 及 `simulated: false`。

## 3. 常用验证命令

修改代码或文档后，请在根目录 `.venv` 虚拟环境中运行对应的检查：

```bash
source .venv/bin/activate
python scripts/check_repository.py
python -m unittest discover -s tests -p 'test_*.py' -v
python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v
python -m unittest discover -s analytics/tests -p 'test_*.py' -v
python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v
python -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v
```

若修改了固件头文件或 `hermes/` 补丁，请同步运行对应子模块的测试（详见 [测试说明](tests/README.md)）。

## 4. 文档与 Git 提交规范

- **文档风格**：保持清晰、自然、易读的技术说明风格，讲清模块定位、实现原理、配置步骤与操作命令，便于后续同学学习与二次开发；避免堆砌空泛套话或重复的免责声明，版本演进直接通过 Git 历史和 [提交学习索引](docs/commit-guide.md) 查阅。
- **细粒度提交**：按功能模块与依赖关系组织原子化的 Git 提交，提交前确保 `python scripts/check_repository.py`、相关测试套件与 `git diff --check` 通过。
