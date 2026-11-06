# 正式固件入口

本项目的两套生产固件统一在本目录维护。源码、协议纯逻辑、构建配置和离线测试均随仓库提供；后续修复与功能更新直接修改对应的正式工程。

| 节点 | 工程 | 职责 | 离线验证 |
| --- | --- | --- | --- |
| `node01` | [Arduino UNO R4 WiFi](arduino-uno-r4/README.md) | 温湿度与光照采集、点阵显示、按钮长按开始录音及松开发送事件 | 39 项 native 测试 |
| `node02` | [ESP32-C3](esp32-c3-ir/README.md) | 红外原始脉冲学习、状态解码、预览及受控发送 | 13 项 native 测试、22 项 Python / C++ 宿主测试 |

两个工程都包含 `src/` 主程序、`include/` 纯逻辑头文件、`test/` 测试与固定依赖版本的 `platformio.ini`。UNO 的断网验证入口也保留在正式工程中，使用单独的 `uno_r4_wifi_outage_test` 环境；日常固件使用 `uno_r4_wifi`。

## 本地配置

按各工程说明从 `include/secrets.example.h` 创建并填写本机的 `include/secrets.h`。真实 Wi-Fi、MQTT 凭据和证书配置由 Git 忽略，不进入提交；构建不会自动退回示例凭据。

实验目录仅用于本机调试资料和历史快照，不作为正式固件源码入口。不要用旧快照覆盖本目录，避免丢失新修复及测试。[原节点导览](esp32-nodes/README.md) 保留为文档兼容入口。

## 离线验证

在仓库根目录运行：

```bash
pio test -d firmware/arduino-uno-r4 -e native
pio test -d firmware/esp32-c3-ir -e native
.venv/bin/python -m unittest discover -s firmware/esp32-c3-ir/test -p 'test_*.py' -v
```

交叉编译、接线与烧录步骤见两个工程各自的说明。ESP32-C3 默认被动启动，开机、待机及网络重连不会自动发射红外；预览也不会发送，实际回放需显式命令。
