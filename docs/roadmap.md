# 项目八周演进路线与扩展方向

本文梳理 **XiaoXi DormSense（交小西宿舍智能体）** 的八周课程开发里程碑，以及后续在此工程基线上可继续深入的扩展方向。

---

## 1. 八周开发里程碑回顾

| 周次 | 阶段主题 | 核心交付成果 |
| --- | --- | --- |
| **第 1–2 周** | 需求定义与契约建模 | 明确宿舍环境感知与语音陪伴目标，完成硬件选型采购（总计 57.64 元），制定 MQTT v1 Topic 规范与 [telemetry.schema.json](../schemas/telemetry.schema.json) 数据契约，搭建仓库与 CI 门禁。 |
| **第 3–4 周** | 模拟链路与 UNO 感知节点开发 | 完成 Python 离线模拟器（`node90`），开发 Arduino UNO R4 WiFi（`node01`）固件，解决 SHT31 串口 CRLF 跨周期切帧与 RA4M1 A0/LED 点阵寄存器锁冲突，实现五幕无闪烁点阵陪伴动效与三线按钮手势。 |
| **第 5–6 周** | 零信任网络隔离与数据滤波治理 | 部署 Mosquitto TLS 8883（含 SKI/AKI 证书链与独立账号 ACL）、`node01-validator` 常驻验证器、`read-gateway` 五实体只读网关與 `inference-egress` 域名白名单代理；上线 HA 24h 滚动保留自动化与一维因果卡尔曼滤波分析工具。 |
| **第 7 周** | 红外波形学习（`learn1`）与安全回放 | 实测抓取原装格力遥控器 280 边沿双段长帧，针对开源库 140 边沿局限转向 `learn1` 原始脉冲学习架构；完成 ESP32-C3 300 项脉冲采集、14 字段状态比对、宿主机 `ir-learning` 服务与两阶段挑战码回放 CLI。 |
| **第 8 周** | 交小西语音、日常单会话与结题整合 | 集成 DeepSeek 推理、本地 Faster-Whisper 语音转写与云端 Edge TTS 小西声线；实现网页端日常单会话自动延续、原生红外学习插件与全套交小西品牌 UI；完成 28 个细粒度 Git 提交、全套文档与结题演示材料。 |

---

## 2. 后续可深入的学习与扩展方向

基于当前的模块化架构，后续同学可以从以下四个方向开展二次开发或课程延伸实验：

1. **将 24 小时卡尔曼滤波报表接入只读网关与智能体工具**
   - 目前 [analytics/src/recorder_report.py](../analytics/src/recorder_report.py) 作为宿主机只读 CLI 运行。后续可在 `read-gateway` 中增加一个受控的只读汇总端点（如 `GET /api/xiaoxi/summary/24h`），让交小西在回答“今天寝室温度变化大不大？”时直接引用 24 小时极值、均值与卡尔曼平滑结果。
2. **结合外部实时天气预报的室内外对比建议**
   - 在 `inference-egress` 白名单中放行合规的公共天气 API 域名（或注册轻量级天气查询插件），将 `node01` 实测的室内温湿度与当地实时气温、湿度、降水概率进行对比，自动生成开窗通风、增减衣物或除湿建议。
3. **物理按钮与网页语音的实时联动体验深化**
   - 利用已接入 Home Assistant 与 `read-gateway` 的 `sensor.xiaoxi_node01_button_event` 实体，在网页端订阅或轮询 `button_double_press` 与 `button_long_press_voice` 事件，实现按下桌面板载微动开关即可直接唤醒浏览器麦克风收音或播报环境状态。
4. **更多宿舍低功耗设备接入**
   - 依托现有的 Mosquitto ACL 与 `validator` 架构，可方便地接入智能台灯（ESPHome / MQTT Light）或蓝牙温湿度计网关，通过扩展 Schema 与网关白名单实现多节点协同感知。
