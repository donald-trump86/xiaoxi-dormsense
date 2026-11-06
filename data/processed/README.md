# 预处理样例数据（`data/processed`）

- 本目录用于存放离线清洗或导出后的 CSV / JSON 汇总文件（本地运行产物不纳入 Git 跟踪）。
- 针对真实运行数据库的 24 小时滑动窗口清洗与一维因果卡尔曼滤波报告，请使用 [analytics/src/recorder_report.py](../../analytics/src/recorder_report.py) 生成。
