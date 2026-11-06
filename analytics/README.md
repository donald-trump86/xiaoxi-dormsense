# 环境历史统计与一维因果卡尔曼滤波模块（`analytics`）

本目录提供针对宿舍温度、湿度、相对光照三路时间序列的 24 小时滑动窗口清洗、基础统计与**一维随机游走因果卡尔曼滤波（1D Causal Kalman Filter）**实现。

---

## 1. 目录结构

| 路径 | 说明 |
| --- | --- |
| [src/environment.py](src/environment.py) | 纯函数核心库：`CausalKalman1D` 滤波器、样本元数据与量程校验、`(boot_id, sequence)` 去重、35 秒断流与重启分段重置、`summarize_history()` 汇总函数 |
| [src/recorder_report.py](src/recorder_report.py) | Home Assistant SQLite（`home-assistant_v2.db`）只读快照分析 CLI，支持按严格 `86,400` 秒窗口提取三路实体并输出 JSON 报告 |
| [tests/test_environment.py](tests/test_environment.py) | 卡尔曼滤波平滑收敛、异常值剔除、断流重置与过期状态抑制测试 |
| [tests/test_recorder_report.py](tests/test_recorder_report.py) | SQLite 只读连接、行数上限保护与跨夏令时 24 小时窗口边界测试 |

---

## 2. 快速运行

```bash
source .venv/bin/activate

# 1. 运行 23 项单元测试
python -m unittest discover -s analytics/tests -p 'test_*.py' -v

# 2. 对本地 Home Assistant 数据库生成 24 小时统计与卡尔曼滤波报告
python -m analytics.src.recorder_report \
  --db deploy/runtime/home-assistant/home-assistant_v2.db
```

算法推导、参数取值与 Home Assistant 24 小时滚动保留策略详见 [历史数据保留与卡尔曼滤波设计文档](../docs/history-and-kalman.md)。
