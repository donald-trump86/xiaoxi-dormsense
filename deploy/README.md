# 本机部署骨架

[compose.yaml](compose.yaml) 提供带密码的 Mosquitto 与可选 `platform` profile 的 Home Assistant。启动不是初始化脚本的一部分；不会自动创建密码、HA 用户或 Token。

完整步骤、安全边界与 Linux/macOS 差异见 [docs/deployment.md](../docs/deployment.md)。运行前必须生成 `mosquitto/passwords`（已忽略）。`runtime/` 包含 HA 的真实用户、Token 和数据库，不可提交。

默认仅绑定 127.0.0.1，因此 **Arduino 无法直接接入该默认端口**。网络联调前需完成 LAN 地址、每节点 ACL、TLS、防火墙与隔离网络评审。严禁简单改为公网监听。

镜像标签是初始选择，不是已验收版本；首轮联调后记录实际 tag/digest、Docker/Compose 与操作系统版本。Hermes Agent 已收编进本文件（`agent` profile），镜像按 manifest digest 锁定，状态存于 named volume 而非宿主机 bind mount；它的来源核查与安全边界见 [hermes/README.md](../hermes/README.md)。

## 启动

```bash
cp .env.example .env                      # 填入本机密码
docker compose --env-file .env -f deploy/compose.yaml up -d mosquitto
docker compose --env-file .env -f deploy/compose.yaml --profile platform up -d   # 含 HA
docker compose --env-file .env -f deploy/compose.yaml --profile agent up -d      # 含 Hermes
```

Hermes 容器**不做 MQTT 客户端**：它只通过 REST 读 Home Assistant，与[架构](../docs/architecture.md)一致。9119 绑 `0.0.0.0` 是有意为之（OrbStack 不在 loopback 转发容器端口，绑 `127.0.0.1` 会导致宿主机浏览器打不开），安全性由强制 `dashboard.basic_auth` 保证——未配置时上游直接拒绝启动，不会以无鉴权状态运行。换到公共网络前请更换该口令。

`hermes-data` 是 named volume 而非 bind mount：HERMES_HOME 内有多个 SQLite 库，跨 virtiofs/9p 的 bind mount 会静默损坏其 WAL。凭据、配置和会话历史都只存放在该卷内，**不要**复制进仓库。
