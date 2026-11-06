# 本地环境初始化指南

本文指导新克隆仓库的同学在 5 分钟内完成本地 Python 虚拟环境、PlatformIO 固件工具链与配置文件的初始化。

---

## 1. 基础软件要求

| 工具 | 推荐版本 | 用途说明 |
| --- | --- | --- |
| Git | 2.39+ | 版本控制与分支协作 |
| Python | 3.11+（兼容 3.13 / 3.14） | 运行桥接服务、红外学习服务、卡尔曼滤波分析与单元测试 |
| PlatformIO Core（`pio`） | 6.1+ | 编译、测试与烧录 Arduino UNO R4 WiFi 及 ESP32-C3 固件 |
| Docker & Docker Compose | Docker 24+ / OrbStack | 运行 Mosquitto、Home Assistant、安全桥接与 Hermes 容器栈 |

> **Apple Silicon (M1/M2/M3/M4) 提示**：Arduino UNO R4 WiFi 使用的交叉编译工具链部分二进制为 `x86_64` 架构，若首次执行 `pio run` 提示 `Bad CPU type in executable`，在终端执行 `softwareupdate --install-rosetta --agree-to-license` 安装 Rosetta 即可。

---

## 2. 初始化 Python 虚拟环境并运行全套测试

在仓库根目录下执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt -r services/bridge/requirements.txt

# 运行静态检查与单元测试，确认本地环境就绪
python scripts/check_repository.py
python -m unittest discover -s tests -p 'test_*.py' -v
python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v
python -m unittest discover -s analytics/tests -p 'test_*.py' -v
python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v
python -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v
```

---

## 3. 初始化开发板固件私钥头文件（本地忽略）

两块开发板的 Wi-Fi 账号密码、Broker 地址、MQTT 凭据与根证书放在本地头文件 `include/secrets.h` 中（已由 `.gitignore` 忽略，不会误提交）：

```bash
# 1. 初始化 UNO R4 WiFi (node01) 配置头文件并运行 native 单元测试
cp firmware/arduino-uno-r4/include/secrets.example.h firmware/arduino-uno-r4/include/secrets.h
pio test -d firmware/arduino-uno-r4 -e native

# 2. 初始化 ESP32-C3 (node02) 配置头文件并运行 native 单元测试
cp firmware/esp32-c3-ir/include/secrets.example.h firmware/esp32-c3-ir/include/secrets.h
pio test -d firmware/esp32-c3-ir -e native
```

在未填写真实 Wi-Fi 和证书前，依然可以直接执行 `pio run -d firmware/arduino-uno-r4 -e uno_r4_wifi` 和 `pio run -d firmware/esp32-c3-ir -e esp32c3` 验证固件编译通过；连接开发板烧录前，将 `secrets.h` 中的占位符替换为实际配置即可。
