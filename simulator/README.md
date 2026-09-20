# 模拟节点

已提供离线 JSONL 生成器和可选的本机 MQTT 发布路径；不模拟传感器驱动，不代表实测。每条遥测均含 `simulated: true`，默认节点 `node90`。网络发布需另行部署和验收，不能把离线测试当作端到端成功。

## 离线（仅 Python 3.11+ 标准库）

从仓库根目录执行：

```bash
python3 simulator/mqtt_node.py --count 3
python3 simulator/mqtt_node.py --count 5 --seed 42 --node-id node91
```

不连接网络，不读取任何凭据，也不等待采样间隔。seed 固定时业务数值可复现；boot_id 每次唯一，因此完整输出并非逐字节相同。timestamp 始终 null，离线 uptime 是合成的 `sequence * interval`；发布时 uptime 是进程实际经过的秒数，但数据值仍为模拟。

## 可选 MQTT 发布

先按[部署文档](../docs/deployment.md)创建带密码的本机 Broker，然后在虚拟环境中：

```bash
python -m pip install -r simulator/requirements.txt
# 仅 source 自己从 .env.example 创建并检查过的本地文件。
set -a
source .env
set +a
python simulator/mqtt_node.py --publish --count 12 --interval 10
```

仅允许 loopback 地址；未提供 TLS，因此拒绝远程主机。`.env` 不会被 Python 自动加载。示例密码占位符被拒绝，失败返回非零；不在日志打印密码。Ctrl-C / 正常结束尝试发送 retained offline；进程被强杀时由 LWT 处理。每个同时运行的模拟器必须有独立 node_id，不能与真实节点共用 ID。

遥测 QoS 0/non-retained，status QoS 1/retained，clean session、30 秒 keepalive。模拟器是有限批次工具，不实现长期守护、断线缓存、完整重连状态恢复或 command 订阅。异常测试期间断网行为需单独记录；生产级固件重连由 B 实现。

协议见 [MQTT v1](../docs/mqtt-protocol.md)。不得将输出重命名为真实实验数据。
