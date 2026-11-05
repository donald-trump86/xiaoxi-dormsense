# 实时桥接服务

四个模块由已验收私有实现按清单整理，正式路径保持原先的仓库相对深度。没有运行配置、口令、证书私钥、抓取结果或整个私有目录的复制。

| 模块 | 职责 |
| --- | --- |
| [validator.py](validator.py) | 验证 node01 Schema/语义、boot/sequence、防重放及订阅握手；将通过的遥测与可用性转发到 validated topics |
| [read_gateway.py](read_gateway.py) | 认证查询端，只读固定二至五个当前实体，投影字段；列表逐个读取指定实体，不访问 HA 全量状态 |
| [inference_egress.py](inference_egress.py) | 只允许固定五个 HTTPS 主机的 CONNECT，拒绝不允许的地址/端口；不解密 TLS |
| [dashboard_ingress.py](dashboard_ingress.py) | 将原 9119 入口转发至固定 Hermes 上游；不提供任意代理 |

网关允许温度、湿度、相对亮度、按钮事件与红外事件；不开放历史、预测、服务调用或状态写入。Hermes 的工具名称或提示规则不能替代这一访问边界。出站主机为既有 Nous 两个域名、DeepSeek 和 Edge 的两个域名，正式化未增加实际运行权限。

## 配置与镜像

使用[固定依赖](requirements.txt)与[运行时镜像](../../deploy/images/runtime/Dockerfile)。构建上下文采取默认排除、逐文件放行，镜像内只包含四个服务、所需 Schema/检查器和依赖清单，不复制运行状态。

validator 和 gateway 通过只读挂载的 JSON 配置启动，要求常规文件、0600 和当前进程属主；UID 为 10001。validator 的水位写入独立持久卷 `/var/lib/xiaoxi`，不是历史数据归档。示例与准备步骤见[部署说明](../../docs/deployment.md)。

## 源码差异

[source-sha256.json](source-sha256.json)记录当前正式模块及测试的 SHA-256。validator、egress 和 ingress 保持原实现；网关新增一项正式修复：HA 将事件变为 `unknown`/`unavailable` 时可能保留旧事件属性，网关现在保留不可用状态并清空投影中的 `event_type`/`detail`，避免五实体列表整体失败或带出旧内容。身份、其他元数据和在线事件校验仍保留。两项回归覆盖两个事件、两种不可用状态、单实体与五实体列表。

该修复只在正式副本和新镜像中验证；本次没有更新正在运行的私有服务。静态 HA 模板与真实 HA 运行渲染、离线 HTTP fixture 与生产网络测试需分别记账。

## 离线检查

在仓库根目录的开发虚拟环境执行：

```bash
python -m unittest discover -s services/bridge/tests -p 'test_*.py'
```

当前 190 项涵盖校验/防重放、握手和清理、HTTP 限制、TLS/地址及代理边界与 HA 模板契约。测试使用合成数据、受控时钟/客户端和本机 fixture，不要求生产凭据，也不等于重新完成硬件或跨容器网络验收。
