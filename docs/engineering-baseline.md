# 正式工程基线与提交分组

2026-11-05 将既有实验实现整理到正式目录，并验证源码、构建配方和测试。已有实验部署继续使用原配置；新模板与新镜像尚未切换上线。本页记录本轮实际完成项，不倒填 Git 历史、团队贡献或实物验收。

## 正式产物

| 范围 | 入口 | 本轮结果 |
| --- | --- | --- |
| UNO 感知、矩阵、按钮 | [固件与说明](../firmware/arduino-uno-r4/README.md) | 主程序、五个头文件和两组测试从既有实验迁移；依赖版本固定，凭据模板为假值 |
| C3 红外收发 | [固件与说明](../firmware/esp32-c3-ir/README.md) | 主程序/逻辑头文件对应已核实源码；单协议单次 `sendAc()`、预览零发送及既有限制保留 |
| MQTT 验证与只读边界 | [四个桥接服务](../services/bridge/README.md) | validator、五实体网关、推理出口及 Dashboard 入口进入正式目录，含测试和源码清单 |
| HA 真实节点 | [配置说明](../home-assistant/README.md) | node01 三个周期通道与 node01 按钮/node02 红外事件共五实体；node90 模拟模板原样保留 |
| 独立部署 | [七角色 Compose](../deploy/compose.secure.yaml)、[部署步骤](deployment.md) | 独立项目、持久卷、只读配置、TLS/ACL 示例、固定镜像与最小构建上下文；没有执行 `up` |
| Hermes | [完整补丁与镜像配方](../hermes/README.md) | 固定上游六文件补丁、前后哈希门禁、35 项语音依赖哈希锁、人格、离线回归与前端构建 |
| 模型前置条件 | [模型清单](../deploy/examples/whisper-base.manifest.json)、[本地校验器](../scripts/verify_whisper_model.py) | 固定公开 revision、文件大小及发布哈希；本轮没有下载或核验真实权重 |
| 数据与分析现状 | [历史与卡尔曼说明](history-and-kalman.md) | 保留被测试使用的样例；说明 HA 持久化、项目历史接口与预测的差别，不新增未验收模型 |

四个桥接模块最初按允许列表逐文件迁移。独立审查发现一处既有问题：HA 离线事件可能保留旧属性，网关因此把整个实体列表判为错误。正式网关现在保留不可用状态并清空返回的旧 `event_type/detail`，增加两项回归；这项修复没有写入私有副本或当前运行实例。[源码清单](../services/bridge/source-sha256.json) 记录正式结果。

Hermes 补丁来自固定上游镜像与完整六文件改动，而非仅迁移最近一次增量。正式转写只保留繁简转换，去掉会把“小溪”等词无条件改成项目名的语义替换。上游完整源码、真实凭据、音频样本、数据库、会话、模型和实测遥测不进入正式构建上下文。

## 实际验证

下表保留工程整理阶段的验收记录，早于同日的一天保留与分析实现；后续根测试为 31 项，另有 23 项分析测试，详见[历史与卡尔曼说明](history-and-kalman.md)。

环境为本机 macOS/OrbStack；正式镜像构建和导入验证针对 Linux ARM64 / Python 3.13。版本固定不等于已测试所有平台，固件也未锁定全部传递工具依赖。

| 检查 | 实际结果 | 能证明的范围 |
| --- | --- | --- |
| 根测试 | 28 通过 | 协议、模拟器、静态集成、正式部署边界与微型模型哈希夹具 |
| 桥接测试 | 190 通过 | 回调、时效、投影、拒绝与有界 HTTP fixture；同组 190 项也在实际正式镜像内通过 |
| Hermes Python | 26 通过 | 请求级声线隔离、兼容性、补丁拒绝、转写语义及依赖门禁 |
| Hermes 侧栏 | 9 通过 | 实际源码回调、当前声线、取消/过期请求和显式错误；不是已登录浏览器测试 |
| UNO native | 34 通过 | 合成 UART、时钟、传输、LED/按钮逻辑 |
| C3 native / AC handler | 3 / 1 通过 | 合成状态、主机编码/解码、预览零发送及拒绝路径；没有物理发射 |
| 目标板构建 | UNO、C3 均通过 | 用临时假配置编译，结束后删除；没有烧录或访问串口 |
| 正式镜像 | runtime、Hermes 均构建成功 | 镜像来源/源码/人格/锁文件校验；Hermes 完整 `tsc` / Vite 构建通过 |
| 镜像隔离检查 | 两套均通过 | 无网络、只读、非 root、移除 capabilities 的一次性 fixture；未挂载生产数据 |
| Compose | 旧版与正式版解析通过 | 模板语法和插值，不证明端口可用、凭据正确或服务能启动 |

本机最终镜像记录为：

```text
xiaoxi/runtime:formal
sha256:3a8f4a6a8a0ce6e3e40ef097174922e77e83f1e313045d501f5bfb608c3fc7d6

xiaoxi/hermes:formal
sha256:bde3a745bd8421e063fed1e0c2ab0487cc02dde902a734686c41b6c2d9359ec7
```

标签可能随后续构建变化，实际部署前应重新核对镜像及配置。详细日志、初次失败记录和本机检查 JSON 保留在被忽略的 `experiments-private/engineering-baseline/`；它们没有作为公共实验数据提交。

构建过程中保留了三类失败记录：runtime 首次探针的 Python 搜索路径错误仅修探针；Hermes 默认解析曾错误报告找不到已发布的版本，后改为隔离配置并使用官方索引与完整哈希锁，原原因未证实；安装后的全局检查发现固定上游镜像已存在 `msal 1.36.0` 与 `cryptography 50.0.0` 的一项冲突。正式门禁只允许这项已核实基线保持不变，新增或未知问题均失败，不宣称全环境依赖无冲突。

## 复查命令

在仓库根目录、已准备虚拟环境与 Docker 的条件下：

```bash
python -m pip install -r requirements-dev.txt -r services/bridge/requirements.txt
python -m unittest discover -s tests -p 'test_*.py'
python -m unittest discover -s services/bridge/tests -p 'test_*.py'
python scripts/check_repository.py

# 需本机已有固定上游镜像；不会连接运行中的 Hermes：
python3 -B hermes/tests/run_offline.py

# 仅构建，不启动服务：
docker build -f deploy/images/runtime/Dockerfile -t xiaoxi/runtime:formal .
docker build -f hermes/Dockerfile -t xiaoxi/hermes:formal hermes

docker compose -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/secure.env.example -f deploy/compose.secure.yaml config --quiet
```

两板 native、目标板构建与 handler 的完整命令见各自 README。首次构建需要获取固定依赖；构建出的占位配置不能连接真实网络。模型校验只读本地文件，不自动下载或放行出口。

## 部署与现场边界

正式模板面向准备好的独立实例，不是覆盖现有 HA/模型配置的一键迁移脚本。独立项目名隔离容器和卷名，但**不会避免默认端口冲突**；应使用另一主机或经过核对的端口配置，并保留既有卷。模板默认 loopback；用于真实板子时还需明确受信 LAN 地址、证书 SAN 和网络可达性。准备步骤见[部署说明](deployment.md)。

Hermes 只持有查询 Token，后端 Token 仅由网关持有；五个固定实体之外、历史和服务写入仍被拒绝。正式 Broker ACL 没有命令发布账户。它不能替代 C3 本地的停用开关：C3 仍保留简化解析、TTL 只查范围、RAM 八条去重及启动发射等已知限制。

人格必须通过官方工作区机制加载，模型须预先备齐、通过固定清单检查并只读挂载。新模板启动、模型实际加载、已登录浏览器录放音和主观音质均未在本轮验收。最新 UNO 固件及按钮双击/长按、独立供电、空调实际响应仍需现场分别记录。历史一次发送回执不能升级为空调状态证明，也不能授权再次发送。

## 建议的提交分组

下列是按最终产物提出的审查边界，**本轮没有 `git add`、commit 或 push**。实际提交时须结合依赖调整顺序、每组复查，不能倒填以前的开发日期或伪装成当时已有细粒度历史。

| 建议主题 | 主要路径 | 对应复查 |
| --- | --- | --- |
| `feat(firmware): add validated UNO sensing source` | `firmware/arduino-uno-r4/` | 34 native 与 UNO 构建；模板/源码比对 |
| `feat(firmware): add ESP32-C3 IR source and host tests` | `firmware/esp32-c3-ir/` | 3 native、handler 及 C3 构建；已知控制限制 |
| `feat(bridge): formalize validated state and query services` | `services/bridge/`、实际 HA 模板、runtime 镜像配方 | 190 测试、源码清单、构建上下文与凭据边界 |
| `feat(hermes): make voice customization reproducible` | `hermes/` | 六文件 SHA、26+9 回归、依赖锁和实际镜像构建 |
| `chore(deploy): add isolated stack and verification` | `deploy/` 正式配置、根构建排除、模型校验器、根测试与 CI | 28 根测试、Compose 静态校验；跨组依赖一并核对 |
| `docs: reconcile current capabilities and data roadmap` | README、相关 docs、data/analytics 说明 | 链接检查、证据口径、未实现历史/预测及 AI 使用披露 |

开始前已有 `.gitignore`、README、架构/硬件/UNO 说明的修改及 `README_EN.md` 删除。本轮保留这些状态；实际提交者应先查看完整 diff，区分先前编辑与新改动，不使用 `git add .` 顺带收走未审查内容。私有实验和真实运行文件继续留在忽略范围。
