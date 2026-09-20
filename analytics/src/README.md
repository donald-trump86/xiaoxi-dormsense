# 可测试分析代码（Planned）

第一个 PR 建议实现接收记录的 Schema/语义校验与去重纯函数，并为重复 sequence、重启 boot_id、timestamp=null、缺失通道与 simulated 分流写测试。然后才增加只读 MQTT 采集循环。

不要直接导入 `scripts/check_repository.py` 充当生产库；它是离线仓库检查器。生产验证逻辑抽取共享模块前由 A/D 协商位置与依赖，保持 [MQTT 契约](../../docs/mqtt-protocol.md)一致。
