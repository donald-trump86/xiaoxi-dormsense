# 一天环境历史与基础估计

目前已实现固定三类 node01 环境数据的 24 小时统计和独立一维卡尔曼估计，输入来自 HA recorder 的只读快照。没有增加常驻采集器、独立原始库、趋势预测、日报服务或 Hermes 历史接口；实时链路仍由[桥接服务](../services/bridge/README.md)维护。

## 使用

只有 Python 标准库即可运行。使用有权限读取实际 HA SQLite 文件的本地主机/容器环境：

```bash
python -m analytics.src.recorder_report --database /path/to/home-assistant_v2.db
```

可直接在存放数据库的环境中执行模块；不要为了运行报告而把整个数据库、Token、私人配置或其他设备历史复制到公开目录。原始 SQLite 文件保持只读，输出只有固定三通道的有界摘要，不输出原始序列或任意实体属性。数据库路径、表结构和访问权限必须与实际 HA 版本匹配。

[recorder_report.py](src/recorder_report.py)仅查询固定实体的 `[now-24h, now]` 状态记录，采用 `mode=ro`、`query_only=ON`、单次快照、超时和 100,000 行上限。JSON 属性重复键、非有限数、异常大小等不能混入有效元数据。

[environment.py](src/environment.py)的 `summarize_history(rows, *, now)` 是无 I/O 纯函数。它检查窗口、`simulated=false`、boot/sequence、接收时间、单位和范围，按通道去重，输出有效数量、最小/最大/均值和当前平滑估计。缺测、重启或超过 35 秒的间断会重置滤波；当前数据达到 35 秒过期时不返回当前估计，历史统计仍明确标为过去窗口。

## 保留策略与参数

[HA 自动化](../home-assistant/automations/environment-retention.yaml)每 5 分钟及 HA 启动时清理这三类实体的一天前状态。三路实体不再声明 `state_class: measurement`，避免另外产生长期统计。现有实例旧统计的一次性清理已经单独验收；新实例不能把普通状态 purge 当成长期统计清理。其他设备历史和项目实验记录不在此策略范围。

查询严格按 86,400 秒截断，物理删除可能滞后 5 分钟加 recorder 队列时间。SQLite 文件也不保证立刻缩小；这里没有全库重打包或备份清理。

各通道使用实际接收时间差 `dt`，初始 `P=r`。当前默认值为：

| 通道 | 每秒过程方差 q | 测量方差 r |
| --- | ---: | ---: |
| 温度 | 0.0001 | 0.04 |
| 相对湿度 | 0.0025 | 0.25 |
| 归一化亮度 | 0.000001 | 0.0001 |

这是便于测试和教学的未标定参数，不是测得的传感器噪声。算法方差不等于经过校准的置信区间；平滑不证明精度提高，也不是未来趋势预测。完整模型、质量规则与评价方法见[历史与卡尔曼说明](../docs/history-and-kalman.md)。

## 验证

```bash
python -m unittest discover -s analytics/tests -p 'test_*.py' -v
```

23 个合成测试覆盖质量、窗口、乱序/重复、间断、手算滤波、只读 SQLite、查询范围和上限等。另有实际 HA 的有界只读报告验收，只保留摘要，不能把一次运行当成完整一天的连续采样、预测精度或参数校准证明。

[requirements.txt](requirements.txt)保留的是后续探索的候选依赖，当前基础报告不需要安装它们。[notebooks](notebooks/README.md)用于探索，不是必须手工运行的生产步骤。
