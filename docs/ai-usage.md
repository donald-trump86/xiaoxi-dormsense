# AI 辅助开发与验证记录

本文件记录项目开发过程中使用 AI 编程助手协助完成的主要模块设计、代码实现与自动化验证工作，方便课程助教与小组成员了解各阶段的技术演进。

---

## 1. 协作原则与质量门禁

在借助 AI 编程助手开展软硬件协同开发时，团队遵循以下四项工程原则：

1. **契约先行，模块解耦**：先定义 [schemas/telemetry.schema.json](../schemas/telemetry.schema.json) 与 [docs/mqtt-protocol.md](mqtt-protocol.md) 数据契约，再并行推进固件、验证器、网关与智能体开发。
2. **纯逻辑抽离，主机可测**：将 Arduino UNO R4 WiFi 与 ESP32-C3 的帧解析、状态机与时序格式化抽离为标准 C++ 头文件（`include/*.h`），在无硬件连接时也能通过 `pio test -e native` 和主机 C++ 编译器执行回归测试。
3. **最小权限与配置脱敏**：所有真实密码、Token 与证书均隔离在 `.gitignore` 忽略目录中，仓库仅跟踪 `.example` 模板，并由 `scripts/check_repository.py` 自动扫描校验。
4. **实测驱动迭代**：硬件接线、传感器分帧、ADC 与点阵寄存器锁冲突、格力 280 边沿双段红外波形学习等方案均根据真实开发板实测结果迭代定型。

---

## 2. 分阶段协作演进记录

### 阶段一：仓库骨架、MQTT v1 契约与离线模拟器
- **完成内容**：建立项目目录结构、MQTT v1 遥测 JSON Schema、Python 离线/本地模拟器（`simulator/mqtt_node.py`）、Home Assistant 示例配置与 `scripts/check_repository.py` 静态检查脚本。
- **自动化验证**：根目录 18 项基础契约与模拟器单元测试通过。

### 阶段二：UNO R4 WiFi 感知陪伴固件与安全桥接服务
- **完成内容**：
  - 开发 `firmware/arduino-uno-r4/`：实现 SHT31 串口 9600 8N1 字节流状态机、LM393 光敏 4 次均值归一化、RA4M1 Port 0 A0 与 12×8 LED 点阵寄存器锁冲突修复、五幕慢速点阵陪伴动画及三线按钮手势扫描。
  - 开发 `services/bridge/`：`validator.py`（遥测契约校验与 `(boot_id, sequence)` 单调水位持久化）、`read_gateway.py`（五实体只读安全网关）、`inference_egress.py`（HTTPS 域名白名单 `CONNECT` 代理）与 `dashboard_ingress.py`（9119 入口转发）。
- **自动化验证**：`firmware/arduino-uno-r4` 34 项 native 测试与 `services/bridge/tests` 190 项单元测试通过。

### 阶段三：24 小时滚动历史保留与一维因果卡尔曼滤波
- **完成内容**：
  - 配置 Home Assistant 自动化 [environment-retention.yaml](../home-assistant/automations/environment-retention.yaml)，每 5 分钟清理温度、湿度、光照三个实体超过 24 小时的历史状态。
  - 开发 [analytics/src/environment.py](../analytics/src/environment.py) 与 [analytics/src/recorder_report.py](../analytics/src/recorder_report.py)，支持从 HA SQLite 数据库只读提取 24 小时有效样本并计算一维随机游走因果卡尔曼滤波平滑估计。
- **自动化验证**：`analytics/tests` 23 项滤波与夏令时窗口边界测试通过。

### 阶段四：ESP32-C3 红外脉冲诊断、学习型遥控（`learn1`）与受控回放
- **完成内容**：
  - 开发 [firmware/esp32-c3-ir/](../firmware/esp32-c3-ir/README.md) 原始微秒脉冲分包导出（`ir_raw_timing.h`）与离线时序分析器（`tools/nec_timing.py`）。
  - 针对格力原装遥控器 `rawlen=280` 双段长帧，升级 `learn1` 学习与回放固件（最高 300 项脉冲采集、14 字段标准空调状态解码、发射期间暂停接收中断、一次性挑战码 `ir_raw_prepare` / `ir_raw_commit`）。
  - 开发宿主机红外学习服务 [services/ir_learning/](../services/ir_learning/README.md) 与第八容器编排 [deploy/compose.ir-learning.yaml](../deploy/compose.ir-learning.yaml)。
- **自动化验证**：C3 固件 22 项主机测试 + 13 项 native 测试、`services/ir_learning/tests` 52 项服务与回放测试通过。

### 阶段五：Hermes 语音交互、日常单会话延续与交小西品牌定制
- **完成内容**：
  - 整理 [hermes/](../hermes/README.md) 可复现构建配方与 16 文件精确补丁（`patches/hermes.patch`），集成 Faster-Whisper 本地语音识别、Edge TTS 云端语音合成、网页端日常单会话自动延续、原生红外学习插件 `xiaoxi_ir_learning` 与交小西全套终端/网页品牌（`xiaoxi · DormSense`）。
  - 编写细粒度 Git 提交学习索引 [docs/commit-guide.md](commit-guide.md) 并完善全仓中文技术文档。
- **自动化验证**：14 项插件测试、31 项根测试，以及无网络容器中的 26 项 Python 补丁测试 + 9 项语音回调测试 + 9 项日常会话延续测试全部通过。
