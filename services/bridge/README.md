# 安全桥接服务模块（`services/bridge`）

本目录包含运行在后端设备网段（`backend`）与智能体内部网段（`agent`）之间的四个轻量级 Python 安全守护进程，统一由非特权容器镜像 [deploy/images/runtime/Dockerfile](../../deploy/images/runtime/Dockerfile)（UID `10001:10001`，只读根文件系统）承载。

---

## 1. 四个核心桥接服务

| 源码文件 | 对应容器服务 | 核心职责与安全机制 |
| --- | --- | --- |
| [validator.py](validator.py) | `node01-validator` | 订阅 `xiaoxi/dorm/node01/{telemetry,status}`，强制执行 10 秒握手截止期、[telemetry.schema.json](../../schemas/telemetry.schema.json) 契约校验及跨字段状态检查；通过 `/var/lib/xiaoxi` 原子文件锁持久化每个 `boot_id` 的最高 `sequence`，防止旧包重放，合格数据转发至 `xiaoxi/validated/node01/#` |
| [read_gateway.py](read_gateway.py) | `read-gateway` | 封存 Home Assistant 后端 Token（`HASS_BACKEND_TOKEN`），仅向 `hermes` 暴露 5 个白名单实体（温度、湿度、光照、按钮事件、红外事件）的只读 `GET /api/states` 接口；聚合查询在后端逐一请求 5 个固定实体并裁剪敏感属性，任何写操作（`POST`）直接返回 `405` |
| [inference_egress.py](inference_egress.py) | `inference-egress` | 为处于 `internal` 网段的 `hermes` 提供 HTTP `CONNECT` 代理（端口 `3128`），仅放行配置文件白名单中的固定 HTTPS 域名（DeepSeek API、Edge TTS 等 `:443` 端口），并拦截私网/回环 IP 解析 |
| [dashboard_ingress.py](dashboard_ingress.py) | `dashboard-ingress` | 将宿主机 `127.0.0.1:9119` 的 HTTP 与 WebSocket 流量安全转发至内部网段的 `hermes:9119` |

---

## 2. 运行单元测试

本模块包含 190 项单元测试（涵盖验证器状态机、网关 HTTP 边界、出口代理域名过滤与入口转发）：

```bash
source .venv/bin/activate
python -m unittest discover -s services/bridge/tests -p 'test_*.py' -v
```
