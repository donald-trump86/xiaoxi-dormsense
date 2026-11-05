# 正式基线部署指南

本页针对**新实例**。[正式 Compose](../deploy/compose.secure.yaml)与现有私有实验部署分开，本次只做源码、镜像与离线验证，没有执行新项目启动或替换旧服务。原[开发 Compose](../deploy/compose.yaml)保留为历史兼容入口，不能单独代表当前七角色隔离部署。

仓库根目录执行命令，先确认 Docker Engine/OrbStack 和 Compose 可用。新项目名隔离容器和卷，**不会隔离宿主机端口**：默认 1883、8123、8883、9119 必须空闲。已有同端口服务时先只做结构/构建检查；并行运行需要单独主机或经审查的端口覆盖，不能直接停掉现有实例。

## 1. 构建前检查

```bash
python -m pip install -r requirements-dev.txt -r services/bridge/requirements.txt
python -m unittest discover -s tests -p 'test_*.py'
python -m unittest discover -s services/bridge/tests -p 'test_*.py'
python scripts/check_repository.py
docker compose --env-file deploy/secure.env.example -f deploy/compose.secure.yaml config --quiet
docker compose --env-file deploy/secure.env.example -f deploy/compose.secure.yaml build node01-validator hermes
```

构建上下文分别为根目录严格白名单与 `hermes/` 严格白名单。桥接镜像默认 UID 10001、只读根文件系统、无 capabilities；validator 的水位使用独立持久卷。Hermes 继承固定上游入口/运行用户，项目补丁先做六文件 SHA 校验，再安装哈希锁定的语音依赖并离线构建前端，详见[Hermes 来源与检查](../hermes/README.md)。

镜像构建不提供 Wi-Fi、MQTT 密码、HA 用户/Token、模型账号或 Whisper 权重。这些是下一阶段的本地前置条件。

## 2. 新实例的私密目录

仅在这些目标不存在时准备，避免覆盖当前根环境文件或任何已有配置：

```bash
umask 077
mkdir -p deploy/runtime/secure/ca deploy/runtime/secure/broker
mkdir -p deploy/runtime/secure/validator deploy/runtime/secure/gateway
mkdir -p deploy/runtime/secure/whisper-base
cp -n deploy/secure.env.example deploy/runtime/secure.env
cp -n deploy/examples/validator.example.json deploy/runtime/secure/validator/config.json
cp -n deploy/examples/gateway.example.json deploy/runtime/secure/gateway/config.json
cp -n deploy/examples/mosquitto-secure.conf deploy/runtime/secure/broker/mosquitto.conf
cp -n deploy/examples/mosquitto-acl.conf deploy/runtime/secure/broker/acl
cp -n deploy/examples/ca.example.cnf deploy/runtime/secure/ca/ca.cnf
cp -n deploy/examples/broker-cert.example.cnf deploy/runtime/secure/broker/server.cnf
```

私下编辑副本。`COMPOSE_PROJECT_NAME` 保持独立；仪表盘使用强口令。网关 `query_token` 与环境文件 `HASS_TOKEN` 必须相同，并与 `backend_token` 完全不同。HA 后端 Token 只进入网关配置，不进入 Hermes 环境、提示规则或镜像。validator 使用独立 `xiaoxi_validator` 账号。

示例值不是已配置的秘密，不应直接上电使用。不要 `source` 不受信文件、在命令参数中填写真实密码、把配置内容输出到终端记录或贴到对话。

## 3. 新 CA 与 Broker 证书

在私下复制的 `server.cnf` 中，将文档占位 IP `192.0.2.1` 替换为实际、经核对的 Broker LAN IP，保留 DNS SAN `mosquitto`。板卡用 LAN 地址，validator 用容器 DNS，两种名称都须能验证。换 LAN IP 后重新核对证书，不关闭验证。

使用支持这些扩展的 OpenSSL，为**全新证书目录**生成：

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -config deploy/runtime/secure/ca/ca.cnf \
  -keyout deploy/runtime/secure/ca/ca.key -out deploy/runtime/secure/ca/ca.crt
openssl req -new -newkey rsa:2048 -sha256 -nodes -subj /CN=mosquitto \
  -keyout deploy/runtime/secure/broker/server.key -out deploy/runtime/secure/broker/server.csr
openssl x509 -req -sha256 -days 365 \
  -in deploy/runtime/secure/broker/server.csr \
  -CA deploy/runtime/secure/ca/ca.crt -CAkey deploy/runtime/secure/ca/ca.key -CAcreateserial \
  -extfile deploy/runtime/secure/broker/server.cnf -extensions server_extensions \
  -out deploy/runtime/secure/broker/server.crt
openssl verify -CAfile deploy/runtime/secure/ca/ca.crt deploy/runtime/secure/broker/server.crt
cp -n deploy/runtime/secure/ca/ca.crt deploy/runtime/secure/broker/ca.crt
cp -n deploy/runtime/secure/ca/ca.crt deploy/runtime/secure/validator/ca.crt
```

CA 和叶子扩展包含 SKI/AKI、用途与约束，避免新 Python/OpenSSL 严格验证拒绝缺失 AKI 的证书。CA 私钥只留在 `ca/`，不放进 Broker 的整个挂载目录，不进入任何镜像。固件私下填入公有 CA 证书、实际地址及各自账号，按[UNO](../firmware/arduino-uno-r4/README.md)和[C3](../firmware/esp32-c3-ir/README.md)操作；本次没有重刷板卡。

## 4. Broker 账号与挂载权限

在相同的固定 Mosquitto 镜像中，挂载**新** Broker 目录到 `/work` 并进入 shell，交互生成密码文件。`-c` 只在文件不存在时对第一个账号使用，后续命令追加账号：

```bash
# NODE01_USER / NODE02_USER 须先替换为 ACL 中对应节点的 user 值。
mosquitto_passwd -c /work/passwords NODE01_USER
mosquitto_passwd /work/passwords NODE02_USER
mosquitto_passwd /work/passwords xiaoxi_validator
mosquitto_passwd /work/passwords xiaoxi_ha_read
```

镜像为 `eclipse-mosquitto@sha256:199ea8ef2e35ec2b1b37e59cfd1dbae538ed4dfa4a2251a121a52215a6248a21`，容器内用户 1883。可选 node90 测试需要另加 `xiaoxi_dev`；它不能写入真实节点。密码文件虽是哈希也保持私密。[默认 ACL](../deploy/examples/mosquitto-acl.conf)没有任何命令发布者，HA 账号只读。C3 固件本身仍有真实发送能力，这份 ACL 不是本地 disarm 开关，也没有修改现有实验账号权限。

validator/gateway 的目录必须可由容器 UID 10001 遍历，配置文件要求该 UID 属主、常规文件和 0600；CA 可读。Broker 文件须供 UID 1883 读取，私钥/密码不放宽为全局可读。先填完配置，再在目标宿主机按实际 UID 映射设定属主和权限。Linux 通常需要对**这次新建目录**设置对应 UID；macOS/OrbStack 文件共享映射须实测，不能机械假定与 Linux 一致，也不能用 `chmod 777` 绕过。

validator 水位在 `validator-state` named volume。第一次创建与已有水位恢复要区别处理；不要删除水位或锁文件来“修复”拒绝，更不能拿空卷替代已初始化状态。

## 5. HA 与只读网关

确认端口、证书、账号、目录权限就绪后，部署人员可先启动新项目的 HA 与 Broker：

```bash
docker compose --env-file deploy/runtime/secure.env -f deploy/compose.secure.yaml up -d mosquitto home-assistant
```

打开 `http://127.0.0.1:8123`，由用户完成账号和必要 MFA。通过 HA UI 添加 MQTT 集成，Broker 为 `mosquitto:1883`，使用 `xiaoxi_ha_read`。这是后端网络内的认证连接；真实板卡走另外的 TLS 8883。

新实例[配置入口](../home-assistant/configuration.secure.example.yaml)加载[真实模板目录](../home-assistant/mqtt/real/node01.yaml)。五个 ID 必须在 UI 核实：

- `sensor.xiaoxi_node01_temperature`
- `sensor.xiaoxi_node01_humidity`
- `sensor.xiaoxi_node01_light`
- `sensor.xiaoxi_node02_ir_event`
- `sensor.xiaoxi_node01_button_event`

已有实例不可覆盖配置或强行重命名旧实体；本模板仅用于新实例。三路周期读数从 validated topics 接收并约 35 秒过期；两个事件记录最近事件，不是周期采样或空调实际状态。[事件模板](../home-assistant/mqtt/real/events.yaml)不是完整的节点事件 Schema 校验器。

用户创建专用后端 HA Token，私下填入 gateway 的 `backend_token`。HA Token 本身不保证只读；真正的读限制由网关和网络执行。完成文件权限后，再启动 validator/gateway。Hermes 只连接 `http://read-gateway:8080`，网关仅接受固定当前状态 GET，没有历史、预测或服务写端点。

## 6. 本地 Whisper 模型

正式镜像不含权重。使用[固定清单](../deploy/examples/whisper-base.manifest.json)中的公开模型 `Systran/faster-whisper-base`、revision `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`，在独立受信主机预先准备四个文件到 `deploy/runtime/secure/whisper-base/`。固定版本源为[模型仓库](https://huggingface.co/Systran/faster-whisper-base/tree/ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66)，不是运行时放开下载域名。

`model.bin` 约 145 MB，清单中的 SHA-256 来自公开 LFS 元数据；三份小文件使用该版本发布的 Git blob SHA-1 与大小，Git blob 哈希包含头部，不能拿普通 `sha1sum` 直接比较。本轮只核对公开元数据，本机直连小文件发生 TLS 失败，未读取现有私有模型或下载权重，不能声称实际模型文件已验证。

准备完成后离线验证：

```bash
python3 -B scripts/verify_whisper_model.py deploy/runtime/secure/whisper-base
```

校验器只读四个规定文件，不下载、不加载模型。通过只证明文件与清单一致，不代表准确率、耗时或麦克风链路已验收。Compose 将目录只读挂到 `/opt/data/whisper-base`，没有文件时不会自动创建空目录来掩盖缺项。运行中的 Hermes 出口不允许 Hugging Face；缓存缺失时上游可能尝试下载，仍应由网络边界拒绝。

## 7. Hermes 人格、工具与语音配置

在独立新项目就绪后启动其余角色。使用官方 `hermes` 入口，以正常 UID 降权路径操作目标 profile，不直接运行安装目录绕过入口，不复制旧容器配置/账号库。模型 Key、HA 查询配置和仪表盘登录由用户通过官方配置入口私下完成。

确认实际 profile 的 `HASS_URL=http://read-gateway:8080`、`HASS_TOKEN` 为查询凭据。活动 profile 的显式值可能覆盖进程环境；不能只看 Compose 环境就宣布迁移成功。后端 HA Token 不进入该 profile。

下列无秘密设置通过官方 `hermes --profile default config set` 配置到目标实例：

```text
platform_toolsets.cli = ["homeassistant"]
terminal.cwd = /opt/xiaoxi/workspace
model.provider = deepseek
model.default = deepseek-chat
model.base_url = https://api.deepseek.com/v1
tts.provider = edge
tts.edge.voice = zh-CN-XiaoxiaoNeural
stt.local.model = /opt/data/whisper-base
stt.language = zh
```

这些是键/值清单，不是可直接粘贴的 shell 脚本。实际命令示例为 `hermes --profile default config set terminal.cwd /opt/xiaoxi/workspace`。上游原生 HA 工具集同时含读与服务工具，网关继续拒绝写操作。`platform_toolsets.homeassistant` 不能替代实际仪表盘 TUI 使用的 `platform_toolsets.cli`。人格已在镜像 `/opt/xiaoxi/workspace/AGENTS.md`，设置工作区后核实加载，并明确创建**新会话**；刷新可能恢复旧提示和旧工具集合。

出口仅允许既有五个 HTTPS 主机：Nous 的 `inference-api.nousresearch.com`、`portal.nousresearch.com`，DeepSeek 的 `api.deepseek.com`，Edge 的 `speech.platform.bing.com`、`api.msedgeservices.com`。源代码固定限制端口与地址，不解密 TLS。若 TUN/Fake-IP 返回特殊网段，先核对 DNS/路由；不得关闭地址验证、TLS 或临时放开任意域名。

浏览器使用 `http://127.0.0.1:9119` 登录，刷新前端并开新会话。其他主机的麦克风通常还要求 HTTPS 安全上下文。用户主动开启语音、同意麦克风权限并检查实际声线显示；物理按钮不能替代浏览器授权。云端失败应显示错误，只有明确选择本机朗读才使用浏览器声音。真实录音、实际播放音质及按钮长按交互仍须现场核对。

## 8. 新实例验收与数据保护

按次序记录独立证据：合法/非法 MQTT 与 CA/地址 → 真实串口/遥测一致 → validator 转发和恢复 → HA 实体/35 秒过期 → 网关固定范围与拒绝写 → Hermes 新会话实际工具 → 麦克风/朗读与按钮 → 电源/断网恢复。镜像构建、静态模板、合成 fixture 和真实物理结果分别记录。

红外节点发送回执不证明空调响应；本模板没有自动空调控制入口，也不因已有发送函数就新增授权。历史/预测能力见[单独方案](history-and-kalman.md)，不通过放开网关历史接口临时补齐。

HA、Hermes、Broker 和 validator 的持久卷均不得随意清空。已有实例迁移先做授权备份与恢复计划，不执行 `down -v` 或覆盖旧配置。公开课程材料只保留审查后的去敏摘要，原始记录、账号、证书私钥和数据库留在本地忽略目录。
