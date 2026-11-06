# 交小西当前天气插件（`xiaoxi_weather`）

这是自写的 Hermes 原生只读插件，通过[中国气象局天气网站](https://weather.cma.cn/)的公开 JSON 端点查询中国城市实况；它不是气象局独立发布的开发者 SDK。无需付费账号、API Key 或额外 Python 依赖，公开网站端点可能随网站更新而改变。

插件注册工具集 `xiaoxi_weather` 和工具 `xiaoxi_get_weather`，只接受可选字符串参数 `city`，默认值为空。返回内容是观测实况，不包含未来预报，也不能根据降水量为零推断晴天。

```json
{}
```

未指定城市时，每次调用都先通过[太平洋电脑网 IP 定位端点](https://whois.pconline.com.cn/ipJson.jsp?json=true)重新取得网络出口所在城市，再用[气象局城市查询端点](https://weather.cma.cn/api/autocomplete?q=%E8%A5%BF%E5%AE%89)查找站号，最后调用[实况端点](https://weather.cma.cn/api/now/V8870)。上面的站号仅为西安接口示例，代码不固定城市或站号，也不缓存或沿用上次位置。

市级 IP 定位可能与用户实际位置不同，尤其在使用代理、VPN、远程服务器或容器网络出口时。插件沿用 Python `urllib` 的代理环境设置，不强制直连，也不要求专用代理；服务能否访问取决于运行环境。定位服务会收到这次连接的网络出口 IP，插件仅读取城市、省份和错误状态，不返回或记录 IP、详细地址、精确坐标。定位失败返回 `weather_location_unavailable`，由助手询问城市。

```json
{"city": "西安"}
```

显式城市会跳过 IP 定位，仅请求城市查询和实况两个端点。中文城市名可带或不带末尾“市”；英文输入须与返回拼音规范化后精确一致，如 `Xian`、`Xi'an`。只选择国家为“中国”的精确唯一结果。没有精确结果或存在歧义时，分别返回 `weather_city_unknown` 或 `weather_city_ambiguous`，并给出最多五个待确认选项，不使用模糊列表的第一项。

成功结果包含 `source`、`source_url`、`location`、`station_id`、`observed_at`、`received_at` 和 `current`。`location_source` 为 `network_ip` 或 `explicit_city`；助手应说明所查城市与观测时间。`current` 只投影以下观测字段：

| 字段 | 单位或含义 |
| --- | --- |
| `temperature_c` | 气温，℃ |
| `humidity_percent` | 相对湿度，% |
| `wind_speed_m_s` | 风速，m/s |
| `wind_direction` | 风向原文 |
| `precipitation_mm` | 接口提供的降水观测值，mm；不推断累计时段 |
| `feels_like_c` | 体感温度，℃ |
| `pressure_hpa` | 气压，hPa；接口缺失时省略 |

气象局的 `lastUpdate` 按中国标准时间解释，两个时间字段均输出带 `+08:00` 的 ISO 格式。观测超过 90 分钟返回 `weather_observations_stale`，超前超过 5 分钟返回 `weather_observations_future`；这两种结果保留来源、地点和时间，但不提供 `current` 数值。没有观测返回 `weather_no_observations`，请求失败返回 `weather_unavailable` 或 `weather_http_error`，格式错误返回 `weather_invalid_response`，响应超限返回 `weather_response_too_large`。错误结果不会暴露异常 URL、请求头或原始页面。

客户端仅访问上述两个固定 HTTPS 域名和固定用途端点，拒绝重定向，保留默认 TLS 验证；每次请求超时 8 秒，响应上限为 128 KiB。定位仅按 UTF-8、GBK 或 GB18030 解析 JSON，不执行 JSONP。观测字段校验类型、有限性和合理范围，拒绝任意 URL 参数。插件不写 Home Assistant、不控制设备，也不保存查询记录。

在仓库根目录运行离线测试：

```bash
.venv/bin/python -B -m unittest discover -s hermes/tests -p 'test_weather_plugin.py' -v
```

测试模拟两个服务的所有响应并阻止 socket 连接；21 项测试覆盖原生注册、动态定位、显式城市、模糊匹配与歧义、字段投影、时效和 HTTP/JSON 错误，不代表在线服务持续可用。
