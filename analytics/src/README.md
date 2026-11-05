# 分析逻辑

[environment.py](environment.py)提供纯函数 `summarize_history(rows, *, now)`，只汇总固定三类环境实体的最近 24 小时记录，执行元数据/单位/范围/时效校验、去重、缺测与 boot/间断重置，再输出统计和独立一维卡尔曼当前估计。它不执行 I/O，不修改输入，不把原始测量替换为模型输出。

[recorder_report.py](recorder_report.py)提供 `read_recorder_history(database, *, now)` 和命令行入口，仅从 HA SQLite 只读查询这三个实体的有界窗口。只在进程内处理原始行，向外输出有界摘要；没有新增 MQTT 采集账号、常驻采集循环或数据库写操作。

使用与参数见[分析说明](../README.md)，模型、实际验收范围和后续预测评估见[历史与卡尔曼说明](../../docs/history-and-kalman.md)。当前没有经过实测验证的趋势预测、插值恢复或 Hermes 历史报告 API。实时 [validator](../../services/bridge/validator.py)仍独立运行，不为每条遥测调用模型。
