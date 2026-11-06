# 课程核心实验设计与复现指南

围绕“**边缘感知—安全传输—数据滤波—智能体交互—红外学习**”的完整闭环，项目设计了 5 个递进式实验，既可在无硬件条件下用模拟器演练，也可连接真实开发板完成全链路实机验证。

---

## 实验总览

| 实验编号 | 实验名称 | 核心验证目标 | 关联模块 |
| --- | --- | --- | --- |
| **实验一** | 端到端感知与语音/文本查询闭环 | 验证 `node01` 串口分帧、TLS 8883 遥测上报、验证器转发、HA 实体更新与交小西自然语言读取 | `firmware/arduino-uno-r4/`、`services/bridge/`、`hermes/` |
| **实验二** | 节点断电/断网检测与恢复实验 | 验证 MQTT LWT 遗嘱、HA `expire_after: 35` 秒自动过期与智能体对不可用状态的诚实反馈 | `home-assistant/mqtt/`、`services/bridge/read_gateway.py` |
| **实验三** | 24 小时滑动窗口与一维因果卡尔曼滤波 | 验证异常样本剔除、断流自动重置及卡尔曼滤波对温湿度与光照量化噪声的平滑效果 | `analytics/`、`home-assistant/automations/` |
| **实验四** | 八容器双网段隔离与最小权限安全实验 | 验证只读网关对写操作的拦截（`405`）、后端 Token 剥离及 HTTPS 出口代理域名白名单 | `services/bridge/`、`deploy/compose.secure.yaml` |
| **实验五** | 空调遥控器 280 边沿长帧学习与挑战码回放 | 验证 ESP32-C3 `learn1` 原始微秒脉冲采集、14 字段前后比对与两阶段安全回放 | `firmware/esp32-c3-ir/`、`services/ir_learning/` |

---

## 实验一：端到端感知与交小西查询闭环

### 1. 实验原理
Arduino UNO R4 WiFi（`node01`）每秒从 `Serial1`（`D0`）接收 SHT31 的 ASCII 温湿度帧（如 `R:057.4RH 024.5C\r\n`），同时通过 `A0` 采集 LM393 相对光照强度，每 10 秒通过 TLS 8883 发布一帧 JSON 遥测。`node01-validator` 校验通过后转发至 `xiaoxi/validated/node01/telemetry`，由 Home Assistant 更新传感器状态，最终通过 `read-gateway` 供交小西智能体实时读取并语音播报。

### 2. 操作与验证步骤
1. **无硬件模拟模式**：
   ```bash
   source .venv/bin/activate
   python simulator/mqtt_node.py --host 127.0.0.1 --port 1883 --count 6 --interval 10
   ```
2. **实机模式**：将 UNO R4 WiFi 接入 USB 供电，观察板载 12×8 LED 点阵按 6 秒/幕轮播笑脸、温度、湿度、光照与暗光 `Zzz` 动画。
3. 在交小西网页端（`http://127.0.0.1:9119`）提问：“现在寝室温度、湿度和光照分别是多少？”，核对回答数值与传感器实测帧一致。

---

## 实验二：节点断连检测、35 秒自动过期与重连恢复

### 1. 实验原理
物联网系统必须区分“**当前实时读数**”与“**传感器已断线留下的陈旧值**”。系统设置了两道保障：
- **MQTT 保活与遗嘱（LWT）**：`keepalive: 30` 秒，断连后 Broker 自动将 `status` 主题更新为 `offline`。
- **采样新鮮度窗口（`expire_after: 35`）**：若超过 35 秒未收到新的合格遥测帧，Home Assistant 自动将温度、湿度、光照实体置为 `unavailable`。

### 2. 操作与验证步骤
1. 记录当前正常上报的 `sequence` 与温湿度读数。
2. 断开 `node01` 电源（或停止模拟器）并计时。
3. 超过 35 秒后，通过 `read-gateway` 或交小西提问“现在寝室多少度？”，验证实体状态变为 `unavailable`，且交小西明确告知当前传感器数据已过期不可读，不会拿旧读数充当实时值。
4. 重新为 `node01` 上电，验证 `boot_id` 递增并在首个采样周期（10 秒内）恢复正常读数。

---

## 实验三：24 小时滚动保留与一维因果卡尔曼滤波实验

### 1. 实验原理
传感器原始采样存在微幅量化跳变（如 `±0.1°C`），且偶发丢包或重启会造成时间间隔不均匀。[analytics/src/environment.py](../analytics/src/environment.py) 采用标量随机游走模型：
- 预测步：$x_k^- = x_{k-1},\; P_k^- = P_{k-1} + q\Delta t_k$
- 更新步：$K_k = \frac{P_k^-}{P_k^- + r},\; x_k = x_k^- + K_k(z_k - x_k^-),\; P_k = (1 - K_k)P_k^-$
当相邻样本间隔 $\Delta t_k > 35\text{ s}$ 或 `boot_id` 改变时，滤波器自动以新样本重初始化，避免跨断流区间产生伪平滑。

### 2. 操作与验证步骤
```bash
# 1. 运行滤波与夏令时窗口边界单元测试
python -m unittest discover -s analytics/tests -p 'test_*.py' -v

# 2. 对 Home Assistant 历史数据库执行只读 24h 统计与卡尔曼滤波分析
python -m analytics.src.recorder_report \
  --db deploy/runtime/home-assistant/home-assistant_v2.db
```

---

## 实验四：八容器双网段隔离与只读网关安全边界验证

### 1. 实验原理
验证智能体容器即使在提示词注入场景下，也无法越权读取非授权实体、无法调用 HA 控制服务、无法访问白名单以外的外部主机。

### 2. 操作与验证步骤
```bash
# 运行桥接安全套件（覆盖只读网关 403/404/405 拦截与出口代理域名白名单）
python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v
```
- 请求 `GET /api/states/sensor.xiaoxi_node01_temperature` → 返回 `200 OK` 及裁剪后的安全字段。
- 请求未授权实体 `GET /api/states/person.admin` → 返回 `404 Not Found`。
- 请求控制接口 `POST /api/services/homeassistant/turn_on` → 返回 `405 Method Not Allowed`。
- 请求非白名单外网域名 `CONNECT evil.example.com:443` → 返回 `403 Forbidden`。

---

## 实验五：空调遥控器双段长帧学习与挑战码安全回放

### 1. 实验原理
通过 ESP32-C3（`node02`）捕获原装格力遥控器的 `rawlen=280` 原始微秒脉冲序列，利用 `IRremoteESP8266` 解码器自动比对前后两帧的 14 个空调状态字段，防止录错按键；回放时通过 `ir_raw_prepare` + `ir_raw_commit` 一次性挑战码握手发射。

### 2. 操作与验证步骤
```bash
# 1. 运行红外学习服务、挑战码回放与 C3 固件测试
python -m unittest discover -s services/ir_learning/tests -p 'test_*.py' -v
python -m unittest discover -s firmware/esp32-c3-ir/test -p 'test_*.py' -v

# 2. 在交小西网页端输入“初始化空调”，按提示依次录制 baseline、power、mode、temp_up、temp_down、fan、swingv
```
录制完成后，可使用受控 CLI [services/ir_learning/replay.py](../services/ir_learning/replay.py) 指定 `profile_id` 与目标按键执行单次红外波形回放。
