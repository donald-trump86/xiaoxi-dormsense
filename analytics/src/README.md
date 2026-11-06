# 分析源码说明（`analytics/src`）

- [environment.py](environment.py)：实现三通道（`temperature`、`humidity`、`light`）样本校验、`(boot_id, sequence)` 去重、35 秒断流分段重置与 `CausalKalman1D` 一维随机游走因果卡尔曼滤波。
- [recorder_report.py](recorder_report.py)：以只读快照模式读取 Home Assistant SQLite 数据库（`states` 与 `state_attributes` 表），输出最近 24 小时（`86,400` 秒）的统计指标与当前卡尔曼滤波平滑状态。
