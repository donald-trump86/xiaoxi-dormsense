# 本机部署骨架

[compose.yaml](compose.yaml) 提供带密码的 Mosquitto 与可选 `platform` profile 的 Home Assistant。启动不是初始化脚本的一部分；不会自动创建密码、HA 用户或 Token。

完整步骤、安全边界与 Linux/macOS 差异见 [docs/deployment.md](../docs/deployment.md)。运行前必须生成 `mosquitto/passwords`（已忽略）。`runtime/` 包含 HA 的真实用户、Token 和数据库，不可提交。

默认仅绑定 127.0.0.1，因此 **Arduino 无法直接接入该默认端口**。网络联调前由 C/A 完成 LAN 地址、每节点 ACL、TLS、防火墙与隔离网络评审。严禁简单改为公网监听。

镜像标签是初始选择，不是已验收版本；首轮联调后记录实际 tag/digest、Docker/Compose 与操作系统版本。没有提供 Hermes 容器，Hermes 按上游官方安装独立配置。
