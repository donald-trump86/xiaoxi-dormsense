# 部署指南

状态：提供 **本机开发配置**，不表示服务已经部署。默认不开放 LAN/公网，也不自动配置 Hermes。Linux 使用 Docker Engine + Compose plugin，macOS 使用已启动的 Docker Desktop 或兼容引擎；先执行 `docker version`、`docker compose version` 确认服务可用。仓库根目录执行下列命令。

## 1. 准备私密配置

```bash
cp .env.example .env
```

在本机编辑 `.env`，把 MQTT_PASSWORD 换成自己的密码，其他凭据按需留空。不得把 .env 发到 PR、聊天或截图。此文件如需 `source`，值必须是合法 shell 赋值（含特殊字符时单引号引用），且仅 source 自己信任的文件。

## 2. 初始化 Broker 密码文件（交互式）

需要拉取官方镜像和可用 Docker 服务。仅首次、密码文件尚不存在时运行；`-c` 会重建密码文件，不要对已有文件重复使用。

```bash
docker run --rm -it --user 0:0 \
  -v "$PWD/deploy/mosquitto:/work" eclipse-mosquitto:2.0 \
  sh -c 'mosquitto_passwd -c /work/passwords xiaoxi_dev && chown 1883:1883 /work/passwords && chmod 600 /work/passwords'
```

按提示输入与 `.env` 相同的密码；命令行不携带明文密码。UID 1883 对应该镜像的 mosquitto 用户，若选用其他镜像须先核实。文件是密码哈希而非明文，仍视为敏感。Linux 挂载权限或 macOS 文件共享异常时先排查日志，**不要改成匿名访问或全目录 chmod 777**。本样例为隔离测试共享账号，按节点 ACL 尚待实现。

```bash
docker compose --env-file .env -f deploy/compose.yaml config --quiet
docker compose --env-file .env -f deploy/compose.yaml up -d mosquitto
docker compose -f deploy/compose.yaml logs --tail 50 mosquitto
```

Compose 只负责服务启动，不把 `.env` 密码写进 Broker；身份认证使用前面生成的文件。本文件中的环境变量主要供本地模拟器/Hermes使用。

先执行[模拟器](../simulator/README.md)的 publish 路径，确认有权限接收、正常断开状态正确，再接 HA。需要独立 MQTT 客户端订阅进行核验，不能仅凭发布进程退出码宣称 HA 收到数据。

## 3. 可选 Home Assistant 本机实例

**仅用于全新测试目录**；已有实例请手工合并，禁止覆盖 configuration.yaml。

```bash
mkdir -p deploy/runtime/home-assistant/mqtt
cp home-assistant/configuration.example.yaml deploy/runtime/home-assistant/configuration.yaml
cp home-assistant/mqtt/sensors.yaml deploy/runtime/home-assistant/mqtt/sensors.yaml
docker compose --env-file .env -f deploy/compose.yaml --profile platform up -d
```

浏览器打开 `http://127.0.0.1:8123` 完成首次用户初始化。通过 Settings → Devices & services 添加 MQTT 集成，Broker 填 `mosquitto`，端口 `1883`，账号 `xiaoxi_dev`，密码为本机设置。容器间使用服务名，不能填 127.0.0.1（那是 HA 容器自己）。等待 HA 加载配置；发生错误时查看日志和其配置检查结果。本仓库静态 YAML 检查不能取代 HA 运行时配置验证。

按[面板说明](../home-assistant/README.md)核实真实 entity_id，再导入示例卡片。先做 node90 模拟链路，真实 node01 映射与固件联调仍 Planned。模拟器结束发 offline 后传感器应不可用，这是正常行为。

## 4. Hermes 独立安装与只读验收

按 [Hermes 集成核查](../hermes/README.md)对应的官方版本安装，不复制上游到此仓库。**只读执行层尚为 Planned；其权限与替代工具绕过测试通过前，不向 Agent 提供真实 HA Token，也不启用原生 homeassistant 工具集。** 当前只能使用人工脱敏的静态资料，并明确不是实时查询。

隔离环境中的只读执行边界完成并经 C/E/F 验收后，才由操作者创建独立的非管理员账号及长期访问 Token，并按经过审查的凭据隔离方案接入。非管理员不意味着细粒度只读；不能简单将 Token 注入同时拥有写工具或任意 HTTP/shell 能力的 Agent。Token 不放 prompts、仓库或 GitHub Actions。

主机访问测试 HA 时 HASS_URL 可为 `http://127.0.0.1:8123`。这只是地址说明，不是启用授权；远程访问需 TLS 与认证网络边界。满足前述门槛后再做真实只读调用验收；控制继续禁用，提示词不是安全隔离。

## 5. 真实 Arduino / LAN 接入前置检查

默认 Broker 端口只绑定 loopback，UNO 无法连接，**这是安全默认值而不是完整无线部署**。由 A/C 明确实验网络、Broker 主机 LAN 地址、Wi-Fi 频段/认证限制、每节点账号与 Topic ACL、TLS 证书及 Arduino 库支持、防火墙后，再另做经审查的配置变更。不要直接取消端口地址限制并暴露给公网。校园 Wi-Fi 可能有设备隔离、Portal 或认证限制，须先确认使用政策；可选授权的隔离实验 AP。

本 Compose 使用端口映射、不依赖 host networking，便于 macOS/Linux 一致开发；不包括 HA 自动发现网络、多播或 USB 透传。镜像 `2.0`/`stable` 尚非锁定可复现版本，首次成功联调应将所测 tag/digest 记录并固定到 PR 中。

## 6. 停止、数据与验收

```bash
docker compose -f deploy/compose.yaml --profile platform down
```

不加 `-v`，保留 Broker named volume；HA 状态在 `deploy/runtime/`。迁移前人工备份并加密，不提交用户数据库、Token 或真实宿舍历史。初始化阶段不执行自动部署或删除数据。

验收清单：拒绝匿名连接 → 合法账号可订阅/发布 → HA 接收标注模拟的三路数据 → 正常退出/强制断网/遥测停止分别验证 offline/expire → 先验证独立只读执行边界（未实现时到此停止）→ 经人工批准接入 Hermes，只读获取同一实体且拒绝控制 → 记录版本、日志与未验证项。真实端到端需用一个已确认实物传感器另行完成。
