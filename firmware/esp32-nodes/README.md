# 固件节点目录导览

项目的两套正式微控制器固件按芯片平台分目录存放：

- **感知陪伴节点（`node01`）**：[../arduino-uno-r4/README.md](../arduino-uno-r4/README.md)（Arduino UNO R4 WiFi，负责 SHT31 串口温湿度、LM393 光照、三线按钮手势与 12×8 LED 点阵动画）。
- **红外学习与回放节点（`node02`）**：[../esp32-c3-ir/README.md](../esp32-c3-ir/README.md)（ESP32-C3，负责空调遥控器 280 边沿长帧原始脉冲学习、14 字段状态比对与挑战码单次回放）。
