# Home Assistant 平台

状态：**配置样例已提供，实例部署与真实设备接入 Planned**。不要覆盖已有 HA 配置。

- [configuration.example.yaml](configuration.example.yaml)：新建测试实例的最小入口。
- [mqtt/sensors.yaml](mqtt/sensors.yaml)：node90 三种模拟读数、JSON availability 和 35 秒遥测过期。
- [dashboards/dorm.example.yaml](dashboards/dorm.example.yaml)：手动面板示例。实体 ID 可能因已有实体冲突而变化，必须在 UI 核实。

操作步骤见[部署指南](../docs/deployment.md)。MQTT 集成的 Broker 地址、用户名和密码通过 HA UI 添加，不把密码写到仓库。HA Compose 内 Broker 为 `mosquitto:1883`；HA 在其他机器时不能使用该 Docker 服务名。

温湿度的 `null` 映射为未知，不沿用旧值冒充有效采样；光照比例不能声明 illuminance/lux。样例模板仅对版本、node90、模拟标志和通道类型/范围做初步门卫，不是完整 JSON Schema 接收验证器（例如未知字段、sensor_status 交叉约束尚未完整校验）。仅允许在隔离 Broker 上消费本仓库受信模拟器；完整校验/隔离坏消息的接入方案由 A/C 在真实设备上线前补齐并验收，不能将离线 Python 校验器的拒绝测试归功于 HA 在线链路。

仅配置只读传感器，没有可控实体、继电器或自动化服务。`expire_after` 不能取代 retained LWT，两者需联调验证。Jinja 模板仍需在实际 HA 版本中检查和加载，静态字符串检查不代表运行验收。

真实 node01 接入、设备分组/MQTT Discovery、历史保留规则、Dashboard 实测验证和安全 LED 场景均 Planned，由 C/F 负责。实体映射冻结后同步给 D/E，Agent 查询必须对 unknown/unavailable 和模拟来源给出解释。
