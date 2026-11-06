# 部署与运行指南

项目提供两套 Docker Compose 部署方案，分别面向**快速本地联调**与**完整八容器安全隔离运行**：

1. **轻量开发联调栈（[deploy/compose.yaml](../deploy/compose.yaml)）**：启动 `mosquitto`、`home-assistant` 与可选的 `hermes`，适合在本地快速测试模拟器或调试单个传感器。
2. **完整安全隔离栈（[deploy/compose.secure.yaml](../deploy/compose.secure.yaml) + [deploy/compose.ir-learning.yaml](../deploy/compose.ir-learning.yaml)）**：启动全部 8 个容器角色（含 TLS 8883、常驻验证器、五实体只读网关、HTTPS 出口白名单代理、9119 入口转发与红外学习服务）。

---

## 1. 方案 A：轻量开发联调栈（`deploy/compose.yaml`）

### 1.1 准备配置目录

```bash
mkdir -p deploy/runtime/mosquitto/config deploy/runtime/mosquitto/data deploy/runtime/mosquitto/log
mkdir -p deploy/runtime/home-assistant deploy/runtime/hermes

cp .env.example .env
cp mosquitto/config/mosquitto.conf deploy/runtime/mosquitto/config/mosquitto.conf
cp home-assistant/configuration.example.yaml deploy/runtime/home-assistant/configuration.yaml
cp home-assistant/automations.example.yaml deploy/runtime/home-assistant/automations.yaml
cp home-assistant/scripts.example.yaml deploy/runtime/home-assistant/scripts.yaml
cp home-assistant/scenes.example.yaml deploy/runtime/home-assistant/scenes.yaml
```

### 1.2 启动基础服务并注入模拟数据

```bash
docker compose -f deploy/compose.yaml up -d

# 向本地 1883 Broker 发送 5 条 node90 模拟遥测消息
source .venv/bin/activate
python simulator/mqtt_node.py --host 127.0.0.1 --port 1883 --count 5 --interval 1
```

启动后访问 `http://127.0.0.1:8123` 完成 Home Assistant 初始化，即可在仪表盘查看模拟温湿度与光照实体。

---

## 2. 方案 B：八容器安全隔离栈（`deploy/compose.secure.yaml`）

完整安全栈实现了设备网段（`backend`）与智能体网段（`agent: internal`）的物理隔离，推荐在接入真实开发板与大模型时使用。

### 2.1 构建本地运行镜像

```bash
# 1. 构建非 root (10001:10001) 桥接与红外学习通用 Python 镜像
docker build -f deploy/images/runtime/Dockerfile -t xiaoxi-dormsense/runtime:local .

# 2. 构建集成语音、日常单会话、红外学习插件与交小西品牌的 Hermes 镜像
docker build -f hermes/Dockerfile -t xiaoxi-dormsense/hermes:local hermes
```

### 2.2 准备 TLS 证书、MQTT 账号与环境变量

1. **环境变量**：将 [deploy/secure.env.example](../deploy/secure.env.example) 复制为 `deploy/.env.secure`（权限 `0600`），填入：
   - `HASS_BACKEND_TOKEN`：供 `read-gateway` 读取 HA 后端实体的长效 Token。
   - `HASS_TOKEN`：供 `hermes` 访问 `read-gateway:8080` 的独立查询凭据。
   - `VALIDATOR_MQTT_PASSWORD` / `IR_LEARNING_MQTT_PASSWORD` / `XIAOXI_IR_LEARNING_TOKEN`：验证器与红外学习服务凭据。
2. **Mosquitto TLS 与 ACL**：
   - 将 [deploy/examples/mosquitto-secure.conf](../deploy/examples/mosquitto-secure.conf) 复制到 `deploy/runtime/mosquitto/config/mosquitto.conf`。
   - 将 [deploy/examples/mosquitto-acl.conf](../deploy/examples/mosquitto-acl.conf) 复制到 `deploy/runtime/mosquitto/config/aclfile`（追加 `xiaoxi_ir_learning` 对 `node02` 的读写授权）。
   - 使用 `mosquitto_passwd` 创建 `passwd` 文件，并生成包含服务器局域网 IP SAN 及 SKI/AKI 扩展的 `ca.crt`、`server.crt`、`server.key`。
3. **Home Assistant 实体与 24h 保留配置**：
   - 将 [home-assistant/configuration.secure.example.yaml](../home-assistant/configuration.secure.example.yaml) 复制为 `deploy/runtime/home-assistant/configuration.yaml`。
   - 复制 [home-assistant/mqtt/sensors.yaml](../home-assistant/mqtt/sensors.yaml)、[home-assistant/mqtt/real/node01.yaml](../home-assistant/mqtt/real/node01.yaml)、[home-assistant/mqtt/real/events.yaml](../home-assistant/mqtt/real/events.yaml) 及 [home-assistant/automations/environment-retention.yaml](../home-assistant/automations/environment-retention.yaml)。
4. **Faster-Whisper 语音模型目录**：
   - 按 [hermes/README.md](../hermes/README.md) 准备本地 `faster-whisper-base` 模型目录，并在提交运行前执行 `python hermes/verify_whisper_model.py <模型目录>` 校验 SHA-256。

### 2.3 启动与状态检查

```bash
# 先校验 Compose 语法与环境变量插值
docker compose --env-file deploy/.env.secure \
  -f deploy/compose.secure.yaml \
  -f deploy/compose.ir-learning.yaml config -q

# 启动八容器安全栈
docker compose --env-file deploy/.env.secure \
  -f deploy/compose.secure.yaml \
  -f deploy/compose.ir-learning.yaml up -d

# 查看各容器运行与健康检查状态
docker compose --env-file deploy/.env.secure \
  -f deploy/compose.secure.yaml \
  -f deploy/compose.ir-learning.yaml ps
```

### 2.4 服务端点一览

| 访问入口 / 内部地址 | 对应容器 | 用途说明 |
| --- | --- | --- |
| `http://127.0.0.1:8123` | `home-assistant` | Home Assistant 管理界面（仅绑定宿主机回环地址） |
| `http://127.0.0.1:9119` | `dashboard-ingress` → `hermes` | 交小西 Web 对话、语音交互与状态面板 |
| `tls://<局域网IP>:8883` | `mosquitto` | 供 UNO R4 WiFi（`node01`）与 ESP32-C3（`node02`）接入的加密 MQTT 端口 |
| `http://read-gateway:8080` | `read-gateway`（仅容器内网） | 仅允许 `GET` 读取 5 个白名单传感器实体的只读网关 |
| `http://ir-learning:8090` | `ir-learning`（仅容器内网） | 供 `xiaoxi_ir_learning` 插件调用的空调按键学习服务 |
| `http://inference-egress:3128` | `inference-egress`（仅容器内网） | 供 `hermes` 访问 DeepSeek 与 Edge TTS 的域名白名单代理 |
