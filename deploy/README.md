# 部署入口

正式源码入口是独立的[compose.secure.yaml](compose.secure.yaml)，包含七种职责：Mosquitto、HA、node01 校验、固定实体网关、Hermes、限定 HTTPS 出口与 9119 入口。完整准备和人工配置步骤见[部署指南](../docs/deployment.md)。本轮只构建/离线验证模板，没有将其应用到现有实例。

[compose.yaml](compose.yaml)保留为历史开发骨架及 node90 模拟教程的兼容入口。实际实验部署还使用本地私有覆盖文件，不能用这个旧文件独自重建当前隔离结构，也不要把新旧 Compose 文件叠加启动。

## 正式基线文件

| 文件 | 用途 |
| --- | --- |
| [secure.env.example](secure.env.example) | 新项目名、loopback 绑定和占位凭据；复制到忽略的 `deploy/runtime/secure.env` |
| [validator.example.json](examples/validator.example.json) | 校验器独立 MQTT 账号、CA 和持久水位路径 |
| [gateway.example.json](examples/gateway.example.json) | 仅网关持有的 HA 后端 Token、独立查询 Token 与固定五实体 |
| [mosquitto-secure.conf](examples/mosquitto-secure.conf) / [ACL](examples/mosquitto-acl.conf) | 已认证的内部 1883 与 TLS 8883，每节点权限；默认没有命令发布账号 |
| [CA](examples/ca.example.cnf) / [服务证书扩展](examples/broker-cert.example.cnf) | 新实例证书模板，含 SKI/AKI；LAN 地址必须私下替换为实际值 |
| [Whisper 清单](examples/whisper-base.manifest.json) | 固定公开模型 revision、文件大小及上游散列；不包含模型权重 |
| [运行时 Dockerfile](images/runtime/Dockerfile) | 明确 COPY 四个服务，构建上下文默认拒绝其余文件 |
| [Hermes Dockerfile](../hermes/Dockerfile) | 固定上游、完整补丁、语音依赖锁与前端构建 |

`runtime/`、密码哈希、配置、证书私钥、HA 数据库和模型文件保持本地忽略。不要把任何现有卷复制到构建上下文。

## 先检查，再部署

以下只使用公开占位配置、解析结构和构建镜像，不启动服务：

```bash
docker compose --env-file deploy/secure.env.example -f deploy/compose.secure.yaml config --quiet
docker compose --env-file deploy/secure.env.example -f deploy/compose.secure.yaml build node01-validator hermes
```

默认项目名 `xiaoxi-review` 隔离容器/卷名称，**不隔离宿主机端口**。1883、8123、8883、9119 与现有部署可能冲突；同机并行运行需要另行审查明确的端口覆盖，或使用独立主机。本次不执行 `up`/`down` 或删除卷。

默认 8883 也只绑定 loopback，真实板卡不能据此从 Wi-Fi 接入。新实例须先核对实验 LAN、Broker IP 与证书 SAN，再配置精确的 `MQTT_BIND_ADDRESS`。不要以关闭 TLS 校验、匿名访问或宽泛公网绑定来代替准备。

Hermes 状态使用 `/opt/data` 的 named volume，模型另外只读挂载；只读网关保存后端 HA Token，Agent 仅持查询凭据。继承上游运行方式，不使用 Docker socket、整个仓库或 HA 目录挂载给 Agent。
