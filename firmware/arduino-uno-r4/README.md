# UNO R4 WiFi 固件（Planned）

负责人 B；A 负责网络和协议协作。尚未添加 `.ino` 或驱动：传感器型号、接线、电压、所用库必须先确认，不能用虚构驱动充当初始化成果。

初期采用 Arduino IDE 2.x + 官方 UNO R4 Boards，原因及确认表见[硬件说明](../../docs/hardware.md)。PlatformIO 是后续验证后的选择，不生成未确认的板卡配置。

首个 PR：填写真实硬件清单，运行一个官方板卡示例，然后完成一个传感器的串口采样。之后拆分定时采样/滤波、WiFiS3网络、MQTT、LED矩阵状态模块，接入[MQTT v1](../../docs/mqtt-protocol.md)。未安装通道发 null，未同步时间发 null，真实样本 simulated=false。

MQTT 库选型需验证 UNO R4 工具链、JSON 序列化、缓冲区、LWT、clean session、QoS 实际支持，记录版本；不得承诺库不支持的 QoS 1 发布。网络失败不能无限阻塞传感器读取。

凭据只写入未跟踪的 `secrets.h`，后续可增加不含秘密的 `secrets.example.h`。不允许硬编码真实 SSID/密码、把个人宿舍信息写入 node_id，或接入高风险执行器。
