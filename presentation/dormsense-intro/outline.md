# 交小西（XiaoXi DormSense）项目介绍提纲

本文件记录 `presentation/dormsense-intro/` 演示文稿的章节结构与视觉素材说明：

1. **封面与项目愿景**：构建面向高校宿舍桌面场景的微环境感知、点阵情绪陪伴与自然语言交互助手。
2. **边缘感知硬件层**：
   - `node01`（Arduino UNO R4 WiFi）：SHT31 串口温湿度、LM393 光敏电阻、三线微动按钮与 12×8 板载 LED 点阵。
   - `node02`（ESP32-C3）：38kHz 红外接收头与 940nm 红外发射头，支持原装空调遥控器 280 边沿长帧波形学习与回放。
3. **安全通信与平台治理层**：
   - Mosquitto TLS 8883 双向校验与最小 ACL、常驻契约验证器 `node01-validator`、Home Assistant 24 小时滚动保留策略与一维因果卡尔曼滤波。
4. **智能体交互层**：
   - 五实体只读网关 `read-gateway`、HTTPS 域名白名单代理 `inference-egress`、本地 Faster-Whisper 语音识别、Edge TTS 小西声线与日常单会话自动延续。
5. **视觉素材与网页入口**：
   - 项目标志图片：[images/xiaoxi-dormsense-logo.png](images/xiaoxi-dormsense-logo.png)
   - 交互式演示页面：[index.html](index.html)
