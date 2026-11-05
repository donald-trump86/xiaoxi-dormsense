# ESP32-C3 红外节点固件

本目录最初整理自私有实验 `experiments-private/real-sht31-wifi/firmware-esp32c3/`，保留运行源码和协议允许列表，此后加入接收缓存诊断、原始时序导出和 `learn1` 学习协议。原有两份测试随源码保留：Unity 测试补齐空的 setup/teardown 钩子，离线 AC handler 测试增加已有库目录的可选环境变量。没有复制上游库、构建产物、私密配置或日志。

正式目录整理时，[src/main.cpp](src/main.cpp) 的 SHA-256 为 `17ccebfe8cf707aeb373a45f4e17faab6c995eb62c4bde05176add7eefaa863b`，与当时提供的生产源码一致。这是历史基线；后续接收缓存修复和 `learn1` 已改变源码。各轮构建、烧录与光学排查结果分开记录于下文，不说明最新 UNO 源码已烧录。

[platformio.ini](platformio.ini) 固定 `platformio/espressif32@6.9.0`、`esp32-c3-devkitm-1`、已安装的 Arduino 框架包 `3.20017.241212+sha.dcc1105b`（Arduino ESP32 **2.0.17**）、IRremoteESP8266 `2.9.0`、PubSubClient `2.8.0` 和 ArduinoJson `6.21.5`；native 为 `1.2.1`，Unity 为 `2.6.1`，并使用同版 ArduinoJson。私有配置的 IR 库约束曾是 `^2.8.6`，实际安装版本为 `2.9.0`，这里按实际元数据固定。源码访问 `_IRrecv::params` 等库内部状态，因此不应随意换库版本。这些固定项不是全部传递工具依赖的锁文件。

## 当前源码行为与限制

- node02 通过 TLS 8883 接入 MQTT，订阅命令，发布状态和事件；发布 QoS 0，LWT QoS 1。GPIO3 发射，GPIO4 接收，接线、电平和发射驱动须按实际硬件核对。
- **当前启动为被动接收。** 已移除 `irsend.calibrate(38000)` 和首次 MQTT 连接后的自动 NEC 自检；上电、重连、`ir_status` 和学习监听不发射红外。显式 `ir_loopback_test` 或串口 `SET_LOOPBACK` 仍可触发 NEC `0x5A02A55A`、32 bit 诊断；学习窗口内拒绝或忽略这些发射入口。
- `ac_preview` 验证允许的协议与状态，重置 `ac.next` 后返回事件，**不调用 `sendAc()`，不因该命令发射红外**。`ac_send` 选择一个协议并调用一次 `sendAc()`，调用期间暂停 RX，结束后用 `enableIRIn(true)` 恢复并清理接收状态。库可能按协议发送多个帧或重复帧；一次函数调用不等于单个物理帧。回执的 `rx_paused=true` 描述代码路径，不是“实测零回波”。
- 原有协议允许列表、16–30°C、模式与风速范围保留。`ac_send` 没有新增本地 disarm 开关；不能把被动启动理解为所有控制入口已关闭，也不说明 HA 安全控制链已经验收。学习窗口内拒绝 `ac_send` 和原始波形准备/提交，`ac_preview` 仍可使用。
- 命令改用固定版本 ArduinoJson 和有界语法检查。[新增学习动作](../../docs/mqtt-protocol.md#61-learn1-命令校验)拒绝未知字段、重复字段、错误类型和越界输入，使用当前 boot 与单调时钟截止时间限制消息时效。所有命令的 `ttl_seconds` 仍须为 1–30，最近 8 个 ID 仅在 RAM 去重；旧 `ac_send` / `ir_loopback_test` 没有新增 boot/deadline 条件，不能把新动作的时效保证套用到旧动作。

## learn1 学习与原始波形回放

主机学习流程、逐键命名、标准库交叉核对、UNKNOWN 人工确认及本地波形保存见[学习服务说明](../../services/ir_learning/README.md)。固件只保存当前学习窗口和待发送波形的有界 RAM 状态，不把学习记录写入 Flash，也不因收到学习帧自动回放。该实验路径没有赋予聊天助手回放权限。

主机先用 `ir_status` 探测 `version=learn1`，取得事件包络中的 `boot_id` 和 detail 中的 `uptime_ms`。这相当于非发射 ping；retained online 状态不能代替当前固件版本与运行段的核对。`ir_learn_start`、`ir_learn_cancel`、`ir_raw_prepare`、`ir_raw_commit` 都要求当前 boot 与 `deadline_ms:uint32`，按 `int32(deadline_ms - millis())` 检查剩余时间必须在 1–10000 ms。主机须基于新取得的设备 uptime 计算截止时间；数值按 uint32 回绕，不能直接使用主机 Unix 时间。命令和会话 ID 限 1–40 个字母、数字、`_`、`-`；主机使用 hex32。

一次 `ir_learn_start` 指定 `session_id` 和 1–60 秒窗口。固件先清理并重新启用接收器，再回 `ready`；已有活动窗口时拒绝覆盖。窗口只消费第一帧，先消耗 arm，再依次发布：

1. `ir_learning` 的 `capture`：`session_id`、`capture`、库报告的 `protocol`、`bits` 和 `state`。
2. `ir_raw_timing` 原始时序分包：保存缓冲最多 300 项，每包 16 项，保留 `rawlen`、截断、溢出和偏移；第 0 项固定为合成 2 μs 哨兵，不是实测空闲间隔。
3. `ir_learning` 的 `complete`：同一 `session_id` 和 `capture`，随后仍可发布既有普通接收诊断。

`capture` 是紧随元数据的首个 raw 分包 sequence；若保留 `kept` 项，则 complete 的 sequence 为 `(capture + ceil(kept/16)) mod 2^32`。到期和匹配取消分别回 `expired`、`cancelled`；取消回执另含 `command_id`。主机不能混合不同 boot、session 或 capture；QoS 0 缺包、`overflow`、`truncated` 或未收到 complete 都不能当作完整学习成功。时序分析工具同时接受旧版最多 160 项的历史记录，不能把旧截断数据解释为当前 300 项完整记录。

标准状态解码成功时，`state` 固定包含 `power`、`mode`、`temp_c`、`fan`、`swingv`、`swingh`、`light`、`turbo`、`econo`、`clean`、`sleep`、`ifeel`、`quiet`、`filter` 共 14 个键；`mode`、`fan`、摆风和 `sleep` 使用 stdAc 枚举/整数，温度为有限摄氏值。GREE 的 `quiet`、`filter` 为 `null`；KELVINATOR 的 `econo`、`sleep`、`ifeel` 为 `null`；其他协议只填已解出的基本电源、模式、温度和风速，其余不确定字段为 `null`。无法还原标准状态时整个 `state=null`，不把库为不支持功能填入的默认值当成实测状态。

固定库保持原容差，并优先尝试严格 Kelvinator 解码。GREE 只解出前 64 bit 时就报告 `GREE/64`，即使同一缓冲有约 280 项 raw，也不能声称完整解出 128 bit；完整 raw 仍保留供主机交叉核对。主机测试已覆盖这种部分解码，但尚无本轮原遥控器实测学习样本。

当前受支持学习回放使用 38 kHz 的 GREE/KELVINATOR 记录。`ir_raw_prepare` 的 `timings_us` **不含哨兵**，长度为 15–299 的奇数，每项为 1–65535 μs 整数，总和不超过 1,000,000 μs，`frequency_khz` 只接受整数 `38`。prepare 只保存 RAM 波形并返回安全随机 hex32 `challenge` 和 uptime 截止值 `expires_ms`，不发射；准备在 10 秒后失效，新的准备覆盖旧值，开始新学习也清理旧准备。

`ir_raw_commit` 使用新的 `command_id`、当前 boot/deadline 和匹配 challenge。固件在发送前取走并清空准备状态，按 `disableIRIn()` → 一次 `sendRaw(..., 38)` → `enableIRIn(true)` 执行，不重试、不追加 repeat，再回 `sent`。旧 challenge、重复 commit 或过期请求被拒绝。`sent` 只说明节点执行了发送路径，不是空调收到或响应的证明。

事件继续使用 schema `1.0` 的 node02 包络、全事件流 sequence、`timestamp=null` 和 `simulated=false`。学习 detail 是**经过外层 JSON 转义的紧凑 JSON 字符串**，不是嵌套对象；detail 上限 512 字节，输出缓冲 1024 字节，完整输入上限 2560 字节，MQTT 缓冲 3072 字节。所有学习状态放在一个 capture detail 内，无额外 state 分包；完整动作和回执字段见[MQTT 契约](../../docs/mqtt-protocol.md#61-learn1-命令校验)。

## 首次构建与离线测试

安装 PlatformIO Core、Python 3 和本机 C++ 编译器后，从仓库根目录执行。首次解析依赖需要下载固定的平台和库；下列步骤没有烧录或串口命令。

```bash
cd firmware/esp32-c3-ir
pio test -e native
# 安装固定的 IR 与 JSON 库源码，供主机离线测试使用，不连接设备：
pio pkg install -e native -e esp32c3
python3 -B -m unittest discover -s test -p 'test_*.py' -v
cp -n include/secrets.example.h include/secrets.h
# 在本机编辑 include/secrets.h，替换全部占位值后再构建：
pio run -e esp32c3
```

凭据只写入已忽略的 `include/secrets.h`，模板是 [secrets.example.h](include/secrets.example.h)。必须填写 `WIFI_SSID`、`WIFI_PASSWORD`、`MQTT_HOST`、`MQTT_USERNAME`、`MQTT_PASSWORD` 和受信 Broker CA PEM `MQTT_CA`；主机须与证书匹配。`.invalid` 主机和 CA 占位内容不能用于连接。源码直接包含 `secrets.h`，不会自动退回模板；native 和主机离线测试均不需要凭据。Python 测试在仓库虚拟环境内执行。

[test_ir_logic](test/test_ir_logic/test_main.cpp) 检查 AC 状态范围、去重/TTL 范围、NEC 匹配和原始时序上限；[test_ir_learning](test/test_ir_learning/test_main.cpp) 检查严格命令解析、boot/deadline 与 uint32 回绕、波形边界、一次性窗口/challenge 及 JSON 转义。[test_ac_handler.py](test/test_ac_handler.py) 提取正式源码中的实际 handler，使用 IRremoteESP8266 的主机测试后端检查 preview 零发送、单次 `sendAc()`、状态重置、Kelvinator 编解码、GREE 关机、拒绝路径及发送成功/失败时 RX 暂停和恢复。旧版成功发送后保留本地回波的断言已改为当前显式 RX 暂停语义，不能据此声称实物无回波。

[test_learning_handler.py](test/test_learning_handler.py) 执行实际 handler、接收和发布函数，覆盖严格 Kelvinator 128 bit、GREE 64 bit 加完整 280 项 raw、UNKNOWN、分包顺序与回绕、取消/到期，以及 prepare 零发送、commit 一次发送和发送前消费 challenge。[test_startup.py](test/test_startup.py) 用离线替身执行实际启动与重连函数，检查没有自动载波或 NEC。主机 IR 测试只编译 Kelvinator/GREE/NEC 子集，不能代表完整允许列表或实物空调兼容性；测试中的 MIDEA 被刻意禁用，用于检查“不支持”拒绝路径。

已有 IRremoteESP8266 `2.9.0` 的本地源码时，可用 `IRREMOTEESP8266_DIR=/path/to/IRremoteESP8266 python3 -B test/test_ac_handler.py` 只读复用，避免下载或复制库；ArduinoJson 仍需按上述步骤安装到 native 依赖目录。native 与主机测试都没有 GPIO、串口、Broker 或真实发射，不能据此宣称硬件重新验收通过。

2026-11-05 正式目录整理验证：`pio test -e native` 3/3、实际 handler 的主机测试 1/1 通过，`pio run -e esp32c3` 构建通过。构建临时使用模板假配置，结束后已删除；占用 Flash 1,154,408 B、RAM 40,956 B。该次整理没有执行 upload、串口连接、MQTT 发布或实物发射；编译产物不等于当前板上二进制。

## learn1 构建、烧录与验收进度（2026-11-05）

当前正式源码与上传用私有源码的 [main.cpp](src/main.cpp) SHA-256 均为 `8c31e4f0f70f3a0faad0bb76c6c535ce538379a66f267188a0ed74dd82835de6`。主机 unittest 22/22、native 13/13 通过；私有项目目标编译通过，占用 Flash 1,168,152 B、RAM 48,804 B。该版只上传一次，upload 退出码为 0。

`node02-learning-flash-20261105` 报告首次因状态查询时节点离线而未通过，不能把该报告解释为上传失败。后续仅连接并查询非发射状态，已收到 `version=learn1`、`boot_id=node02-00000016`、`uptime_ms=208851`，并确认 online 为 true。此次查询没有启动学习窗口、发射 NEC 或重放空调波形。

尚未用原遥控器完成真实学习捕获，也未做 AC 波形回放或验证空调响应。主机服务、聊天插件与能力目录的验收另行记录，不能由固件编译、online 或 `sent` 回执推定通过。

## 接收缓存修复与对射结果（2026-11-05）

本节保留 `learn1` 之前的对射排障记录；当前发送采用前述 RX 暂停/恢复流程，不再用发送后的本地回波作成功条件。

2026-11-05 后续一次获准的 GREE 对射记录到 140 个接收边沿，但发送分支立即调用 `resume()` 清掉了数据。当次修复只移除成功分支的这次提前清理，让现有 `poll_ir_receiver()` 解码；初始重新接收、发送失败清理及原有 60 ms 停止状态兜底保持原职责。

该轮正式和私有上传源码相同，SHA-256 为 `603a691158004ff1d1c2eaeacfcdc617cc55f293d787ff11372a8e18613b422d`。新增合成缓存检查在原代码上因 `rawlen == 140` 失败，修复后 handler 测试 1/1、C3 native 3/3 及私有项目目标编译通过。该编译占用 Flash 1,155,432 B、RAM 40,956 B，使用现有私有配置，未复制配置内容到正式目录。

用户确认 USB 连接和发射条件后，修复已成功烧录。启动 NEC 自检收到 68 个边沿，结果为 UNKNOWN，初次保护流程因此没有发送 GREE。随后承接尚未使用的那一次获准 GREE 复测：发送回执记录 142 个边沿，紧随其后的接收事件也记录 rawlen=142，但结果仍为 UNKNOWN、ac=none，未验证开机/制冷26°C/自动风的完整目标状态。

当次实物结果说明修复后的接收缓存能进入解码/事件路径，不能说明波形格式、空调兼容性或电源已验收，也不保证重复帧无丢失。该轮没有追加重试。随后获准进行的原始脉冲采样见下节；当时重新上电包含既有校准与 NEC 发射，须纳入测试协调。当前 `learn1` 已移除这两项自动发射。

## 有界时序采样与 NEC 离线对照（2026-11-05）

本节是 `learn1` 之前的一次启动诊断及其离线分析；保留失败样本与合成对照，不代表当前启动仍会发码。该版 `setup()` 仍调用 `irsend.calibrate(38000)` 输出校准载波，首次 MQTT 连接约 800 ms 后自动发送一次 NEC `0x5A02A55A`、32 bit 自检；两者均为真实发射。

当时的 [ir_raw_timing.h](include/ir_raw_timing.h) 把接收库保存缓冲中的 tick 转为微秒，最多保留 160 项、每包 16 项，沿现有 TLS 事件 Topic 发送 `ir_raw_timing`，包含原长度、截断、溢出和分包偏移。第 0 项是库生成的 2 μs 哨兵，不是实测空闲间隔；其余时长没有保存电平极性，不能单凭它们判断接线反相。达到 131070 μs 表示触及整数存储上限，不能称为光学饱和。当前学习上限为前述 300 项，分析器保留 160 项历史兼容。

该版只有内部启动调用的显式 `capture_raw=true` 才启用一次导出；命令 ID 即使写成 `boot_selftest` 也不能启用。标志在发布前清除，数据来自 `decode_results` 的保存缓冲。分包之后仍发布普通接收事件，未增加红外发送次数、改变载波或放宽解码容差。发布为 QoS 0、无保留、无重试；解码失败或分包丢失都可能没有完整样本，不能据此断言没有收到红外。当前单帧学习由 `ir_learn_start` 显式开启，不依赖启动自检。

[nec_timing.py](tools/nec_timing.py) 只读分析已保存的事件 payload 数组：按同一 boot/capture 组包，检查连续分包与序号，拒绝重复、冲突、缺包、越界及格式错误，再与固定库的 NEC 时序比较。它不是新的协议解码器，也不连接设备或发送消息。输入文件仅为 JSON 数组，不是外层实验报告；原始实测事件留在私有实验目录。示例命令从本目录执行：

```bash
python3 -B tools/nec_timing.py /path/to/events.json --boot-id node02-00000012 --capture-sequence 1
python3 -B -m unittest discover -s test -p 'test_*.py'
pio test -e native
```

该轮新增 [分包主机回归](test/test_raw_publisher.py) 编译实际发布函数并使用合成保存缓冲，检查一次性启用、伪造命令 ID、长度和包络上限、离线及无数据分支；[分析器回归](test/test_nec_timing.py) 检查组包、单位、容差和异常拒绝。当时加上原有 handler，共 19 项主机测试、6 项 native 测试；当前测试数量见 `learn1` 验证记录。这些合成检查不代表光路或网络实测。

该轮正式/私有源码相同，SHA-256 为 `95691266bc2513a934643393b6bb6308c9104b2745781e66d09d5c8fb0a68205`；私有目标编译占用 Flash 1,155,914 B、RAM 40,956 B。已获准上传一次且成功，使用既有启动校准和一次 NEC 自检，观察程序没有发布 MQTT 命令或追加空调试码。启动前 rawlen=0，实际收到完整 5 个分包和随后的普通接收事件：68 项包含 1 项哨兵及 67 项帧内间隔，无截断、溢出或存储上限值。

只有第一位数据的零空隙异常：标称 560 μs，当前解码窗口 382–638 μs，实际记录 1210 μs；其余 66 项帧内间隔都在对应窗口内。板上结果为 UNKNOWN。用固定库的主机 NEC/HASH 解码子集回放原始数组，复现相同 UNKNOWN 哈希；仅在标明为合成对照的副本中将这一项替为 560 μs，即严格解出预期 NEC `0x5A02A55A`。原始证据没有改写，合成对照没有发射或烧录到设备。

因此，这一个异常间隔足以解释**本次样本**的 NEC 拒绝；尚不能解释它为什么变长，更不能据此宣称空调控制修复。区分发送调度、接收模块输出和中断采样，需要独立测量发射端与接收端的时序。未据此放宽容差、换电源、调整载波或继续发码。

后续对同一原始数组做容差离线对照：25% 仍为 UNKNOWN；26% 则被严格解成错误的 NEC `0xDA02A55A`，地址由预期 `0x405A` 变成 `0x405B`。这是解码参数的反事实对照，未改变原始时长或设备配置；能通过校验不代表数据正确，不能用放宽容差掩盖本次异常。

源码核查确认固定库使用软件 GPIO 载波和忙等空隙，接收依赖 GPIO 中断内的 `micros()`，没有启用 C3 的 RMT 发射。任务或中断延迟只是候选原因，未证明由 Wi-Fi 导致；当时的校准偏移只作用于载波周期。用户当时没有逻辑分析仪或示波器，后续排查方向是先检查既有接线、共地与接触状况；仪器测量是进一步区分原因的方式，不是检查接线的前提。该轮后续检查未新增发码、烧录或固件改动；随后的 `learn1` 构建与单次上传另列于上文。
