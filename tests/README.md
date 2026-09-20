# 验证范围

先在根目录虚拟环境安装 `requirements-dev.txt`，再运行：

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/check_repository.py
```

- `mqtt/`：Schema、UTC/null 时间、缺测、字段/Topic 一致性和非法值拒绝。
- `simulation/`：离线模拟 CLI、序列、启动 ID、可复现合成值、参数错误。
- `integration/`：**静态** HA/Compose/Mosquitto 配置一致性，不是在线系统集成。
- 检查脚本：仓库内 Markdown 相对链接目标存在、JSON 解析、Schema/样例、YAML 语法（识别 HA `!include`）。不验证远程链接、页内锚点或完整 HA 配置语义。

全部测试离线，不运行 Docker，不连接真实设备、不发送 Token、不验证 Hermes 实例。实际 MQTT QoS/LWT、网络异常、HA 实体加载、Hermes 读取与控制拒绝测试须按[实验方案](../docs/experiments.md)与[部署指南](../docs/deployment.md)补充；未完成时 PR 必须写“未验证”。
