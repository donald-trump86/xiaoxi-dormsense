# 容器编排与部署配置（`deploy`）

本目录包含项目的 Docker Compose 编排文件、非特权运行时镜像构建配方以及安全配置模板。

---

## 1. 核心文件说明

| 文件路径 | 用途说明 |
| --- | --- |
| [compose.yaml](compose.yaml) | 轻量开发联调栈（`mosquitto` + `home-assistant` + 可选 `hermes`），适合本地快速测试模拟器 |
| [compose.secure.yaml](compose.secure.yaml) | 七角色双网段安全隔离基线栈（`mosquitto`、`node01-validator`、`home-assistant`、`read-gateway`、`hermes`、`inference-egress`、`dashboard-ingress`） |
| [compose.ir-learning.yaml](compose.ir-learning.yaml) | 第八角色叠加编排文件：启动 `ir-learning` 宿主机红外学习服务并接入 `backend` 与 `agent` 网段 |
| [images/runtime/Dockerfile](images/runtime/Dockerfile) | 构建以非特权用户 `10001:10001` 运行的 Python 桥接与红外学习服务通用镜像 |
| [secure.env.example](secure.env.example) | 安全栈环境变量模板（复制为本地 `deploy/.env.secure` 后填入实际 Token 与密码） |
| [examples/](examples/mosquitto-acl.conf) | Mosquitto TLS 配置、最小权限 ACL、验证器/只读网关配置及 Whisper 模型校验清单示例 |

---

## 2. 常用命令

```bash
# 校验安全栈与红外学习叠加编排语法
cp deploy/secure.env.example deploy/.env.secure
docker compose --env-file deploy/.env.secure \
  -f deploy/compose.secure.yaml \
  -f deploy/compose.ir-learning.yaml config -q
```

详细部署流程请参阅 [部署与运行指南](../docs/deployment.md)。
