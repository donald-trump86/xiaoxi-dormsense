# 24 小时历史数据保留与一维因果卡尔曼滤波

本文介绍项目如何管理 Home Assistant 的传感器历史数据体积，以及如何利用 [analytics/](../analytics/README.md) 模块对温湿度与光照时间序列进行清洗、统计和一维因果卡尔曼滤波平滑估计。

---

## 1. 为什么需要滚动保留与卡尔曼滤波？

`node01` 每 10 秒上报一次温度、湿度和光照（每天单通道约 8,640 条记录，三通道合计约 2.5 万条状态变化）。在长期运行中需要解决两个问题：

1. **数据库体积控制**：如果不加限制地保留所有原始采样点和长期统计汇总表，SQLite 数据库（`home-assistant_v2.db`）会持续增长。同时，聊天记录、配置与其它实体状态又需要正常保留。
2. **量化跳变与断流处理**：SHT31 串口读数（分辨率 `0.1°C` / `0.1%RH`）与 LM393 ADC 读数在稳态附近会出现微幅抖动；若直接做全窗口简单均值，无法反映最新时刻的即时状态；若不识别 35 秒断流与设备重启，则会在断线重连处产生错误的跨区间插值。

---

## 2. Home Assistant 24 小时精准滚动保留策略

配置文件位于 [home-assistant/automations/environment-retention.yaml](../home-assistant/automations/environment-retention.yaml) 与 [home-assistant/mqtt/real/node01.yaml](../home-assistant/mqtt/real/node01.yaml)：

- **仅针对三个高频环境实体**：
  - `sensor.xiaoxi_node01_temperature`
  - `sensor.xiaoxi_node01_humidity`
  - `sensor.xiaoxi_node01_light`
- **每 5 分钟自动清理**：HA 自动化在启动时及每 5 分钟调用一次 `recorder.purge_entities`（`keep_days: 1`），仅清理上述 3 个实体 24 小时前的历史状态，不影响其它实体或 Hermes 对话数据库。
- **不生成冗余长期统计表**：上述 3 个实体省略了 `state_class: measurement`，避免 HA Recorder 额外写入每小时/每日的永久统计汇总表（`statistics` / `statistics_short_term`）。

---

## 3. 样本清洗与一维因果卡尔曼滤波算法

实现源码位于 [analytics/src/environment.py](../analytics/src/environment.py)，由纯函数 `summarize_history()` 与 `CausalKalman1D` 组成。

### 3.1 严格样本筛选与去重规则
在进入统计与滤波前，读取器对 24 小时窗口（严格按 `start = end - 86_400` 秒计算，不受夏令时跳变影响）内的原始记录执行四步过滤：
1. **状态与数值校验**：剔除 `unavailable`、`unknown`、非有限浮点数及超出物理量程的记录。
2. **真实硬件与单位校验**：仅保留属性中 `simulated is False`、包含合法 `boot_id` 与非负整数 `sequence`、且单位匹配（`°C`、`%`）的真实样本。
3. **主键去重**：同一 `(boot_id, sequence)` 若被 HA 重复记录，仅保留首次观测点。
4. **断流与重启分段（Segment Reset）**：当相邻有效样本的时间差 $\Delta t > 35\text{ s}$（超过传感器过期阈值）或 `boot_id` 发生切换时，记录一次间断（`gap_count` / `boot_resets`）并重置卡尔曼滤波器状态。

### 3.2 标量随机游走卡尔曼滤波模型
对每个连续采样段内的第 $k$ 个观测值 $z_k$（时间间隔 $\Delta t_k = \max(t_k - t_{k-1},\; 10^{-3})\text{ s}$）：

1. **段首初始化（$k = 0$）**：
   $$\hat{x}_0 = z_0,\quad P_0 = r$$
2. **一步预测（Predict）**：
   $$\hat{x}_k^- = \hat{x}_{k-1},\quad P_k^- = P_{k-1} + q \cdot \Delta t_k$$
3. **测量更新（Update）**：
   $$K_k = \frac{P_k^-}{P_k^- + r},\quad \hat{x}_k = \hat{x}_k^- + K_k (z_k - \hat{x}_k^-),\quad P_k = (1 - K_k) P_k^-$$

默认参数配置（`DEFAULT_SPECS`）：
- **温度（`temperature`）**：过程噪声功率谱密度 $q = 10^{-4}\text{ °C}^2/\text{s}$，测量噪声方差 $r = 0.04\text{ °C}^2$（对应标准差 $0.2\text{ °C}$）。
- **相对湿度（`humidity`）**：$q = 2.5 \times 10^{-3}\text{ \%}^2/\text{s}$，$r = 0.25\text{ \%}^2$（对应标准差 $0.5\%$）。
- **相对光照（`light`）**：$q = 10^{-6}\text{ s}^{-1}$，$r = 10^{-4}$。

当窗口末端最新样本距评估时刻不超过 35 秒（`fresh: true`）时，报告输出当前滤波平滑值 `smoothed_current_state` 与最新原始值 `raw_current_state`；若最新样本已超过 35 秒，则自动将当前估计置为 `null`，避免输出过期状态。

---

## 4. 命令行运行与输出示例

[analytics/src/recorder_report.py](../analytics/src/recorder_report.py) 使用 SQLite 只读快照模式读取 HA 数据库，不会阻塞正在运行的 Home Assistant 容器：

```bash
source .venv/bin/activate

# 分析默认路径 deploy/runtime/home-assistant/home-assistant_v2.db
python -m analytics.src.recorder_report

# 或显式指定数据库路径与窗口小时数
python -m analytics.src.recorder_report \
  --db deploy/runtime/home-assistant/home-assistant_v2.db \
  --window-hours 24
```
