"""Template-aligned slide copy and editable scene definitions."""
def populate(add, P, groups, purchases):
    blue, cyan, ink, quiet, pale, white = (P[k] for k in ('blue','cyan','ink','quiet','panel','paper'))
    def box(s,x,y,w,h,title,body='',fill=None,size=34):
        fill=fill or blue
        s.rect(x,y,w,h,fill,r=10)
        s.text(title,x+12,y+22,w-24,size,white,True,align='center')
        if body:s.text(body,x+20,y+80,w-40,26,white,align='center')
    def band(s,text,y=748):
        s.rect(80,y,1440,64,pale)
        s.text(text,104,y+14,1392,28,ink)
    def row(s,a,b,y):
        s.text(a,90,y,390,36,blue,True)
        s.text(b,490,y+3,1010,31)

    s=add('交小西 DormSense',15,
        '各位老师好，我们是交小西项目组。我们的作品是一套放在宿舍桌面上的智能体：它能感知温湿度和光照，用点阵显示状态，也能通过语音交流。下面从硬件、无线通信和智能体三个部分，介绍我们怎样把它做出来。',
        ['宿舍环境感知与语音交互','无线传感课程结题答辩'],['README.md'],kind='cover')
    s.text('交小西 DormSense',640,344,850,72,blue,True,align='center')
    s.text('宿舍环境感知与语音交互',655,455,805,39,blue,True,align='center')
    s.text('2026 年 11 月 · 结题答辩',650,672,520,29)
    s.text('交小西六人组',1170,672,350,29)

    s=add('汇报内容',10,
        '先介绍为什么做交小西，以及它与智能音箱的侧重点有什么不同；再看两块开发板怎样通过MQTT交换数据；然后说明点阵、语音和红外的实现；最后进行实物演示。',
        ['项目定位','硬件与 MQTT','点阵与智能体','成果与实物演示'],['README.md'],kind='contents')
    for y,title in [(320,'项目定位'),(452,'硬件与 MQTT'),(586,'点阵与智能体'),(720,'成果与实物演示')]:
        s.text(title,400,y,480,42,ink,True)

    s=add('让宿舍环境，变成看得懂的反馈',25,
        '做这个项目的起点，是把散落的读数变成一个容易交流的桌面伙伴。SHT31采集温度和湿度，光敏模块感知明暗，点阵直接显示数字和表情。想进一步了解环境时，就问交小西。这样我们把传感、无线传输和人机交互串在了一起。',
        ['温湿度与相对光照采集','点阵直接显示数字和表情','通过语音查询宿舍环境'],['docs/hardware.md','schemas/telemetry.schema.json'])
    s.head('从传感器读数，到桌面反馈，再到自然语言交流。')
    for x,value,unit,label in [(90,'24','℃','温度'),(600,'55','%RH','湿度'),(1110,'46','%','相对亮度')]:
        s.text(value,x,282,305,120,blue,True,font='Arial')
        s.text(unit,x+235,367,130,32)
        s.text(label,x+4,450,385,37,ink,True)
    for x,t in [(100,'感知环境'),(625,'点阵反馈'),(1160,'语音交流')]:s.text(t,x,620,320,42,ink,True)
    s.arrow(400,650,560,650);s.arrow(925,650,1090,650)
    s.text('界面数值示例 · 光照采用 0–1 相对值',90,770,1400,25,quiet)

    s=add('和小度相比，我们更想做什么？',40,
        '小度等商业智能音箱，主要把语音交互和成熟的智能家居生态做成开箱即用的产品。交小西的重点，是把一套宿舍无线感知系统从底层搭起来：自己采集数据，自己设计MQTT消息，再让Hermes按需调用工具读取这些数据。我们还可以改点阵表情、按钮交互和红外学习流程。对我们来说，这个项目既是一个桌面伙伴，也是一套能够继续学习和扩展的课程作品。',
        ['商业音箱：语音入口与智能家居生态','交小西：自建传感节点、MQTT 与智能体工具','从硬件到交互，按宿舍需求修改'],['README.md','hermes/workspace/AGENTS.md','https://dueros.baidu.com/didp/doc/dueros-bot-platform/dbp-smart-home/2-iot-quick-get-start/2-1-quick-get-start_markdown'])
    s.head('同样通过语音交互，设计起点和接入方式各有侧重。')
    s.rect(80,242,1440,85,blue)
    for text,x,w in [('比较维度',106,230),('小度等商业智能音箱',397,475),('交小西 DormSense',972,510)]:s.text(text,x,263,w,34,white,True)
    rows=[('使用定位','家庭语音入口、内容与设备服务','宿舍感知与智能体课程作品'),('设备接入','按平台协议与生态接入设备','自建 UNO / C3 节点，MQTT 接入'),('环境数据','通过已接入的设备与服务获取','SHT31 温湿度、LM393 相对光照'),('开发方式','围绕平台技能与设备能力开发','修改固件、点阵、工具与交互')]
    for i,(a,b,c) in enumerate(rows):
        y=327+i*94
        s.rect(80,y,1440,94,pale if i%2==0 else white)
        s.text(a,106,y+28,230,31,blue,True)
        s.text(b,397,y+29,545,29)
        s.text(c,972,y+29,520,29)
    s.text('我们希望把“采集—传输—读取—反馈”这条链路掌握在自己手里。',90,759,1420,31,blue,True)

    s=add('两块开发板，分开处理感知和红外',45,
        'node01使用UNO R4 WiFi。SHT31通过串口送来温湿度，LM393接到A0采集光照，三线按钮负责手势，12乘8点阵显示状态。node02使用ESP32-C3，专门处理红外接收、学习和发射。两块板通过Wi-Fi连接同一个消息服务。供电从一根USB进入UNO，再由5V和GND分配给共地支路。',
        ['node01：感知、按钮、点阵','node02：红外接收、学习、发射','Wi-Fi 传数据，USB 与 5V 支路供电'],['docs/hardware.md','firmware/arduino-uno-r4/src/main.cpp','firmware/esp32-c3-ir/src/main.cpp'])
    s.head('node01 感知环境，node02 负责红外时序。')
    s.rect(80,250,880,427,blue,r=15)
    s.text('UNO R4 WiFi',120,277,720,45,white,True,font='Arial')
    s.matrix('happy',535,357,350)
    s.text('SHT31 → D0 / UART\nLM393 → A0\n三线按钮 → D2 / D3 / D4',120,392,425,30,white)
    s.text('node01 · 环境与点阵',120,601,700,31,white,True)
    s.rect(1055,295,465,337,cyan,r=15)
    s.text('ESP32-C3',1090,329,390,45,white,True,font='Arial')
    s.text('GPIO4 · 红外接收\nGPIO3 · 红外发射\n38 kHz 载波',1090,421,390,31,white)
    s.text('node02 · 红外节点',1090,563,390,29,white,True)
    band(s,'单 USB 输入 → UNO 5V / GND → 共地供电支路；两块板经 Wi-Fi 传输数据。')

    s=add('MQTT：无线节点怎样交换消息',55,
        'MQTT是一种轻量的发布订阅消息协议，适合物联网设备。我们可以把Broker理解为消息分发站：节点把消息发布到一个主题，服务订阅需要的主题，Broker就把消息转过去。发布者和订阅者通过主题对接，彼此不需要知道对方的网络地址。项目中，Wi-Fi负责让开发板接入网络，MQTT运行在TCP连接上，负责组织和分发消息；我们使用TLS加密连接。这样采集端、校验服务和平台可以独立运行，后面增加节点也能沿用同一套方式。',
        ['发布者：向指定 Topic 发送消息','Broker：按 Topic 分发消息','订阅者：接收自己关心的主题','Wi-Fi 接入网络，MQTT 组织消息'],['docs/mqtt-protocol.md','deploy/examples/mosquitto-secure.conf'])
    s.head('发布 / 订阅：设备按主题发消息，服务按主题收消息。')
    box(s,80,330,340,175,'发布者','UNO / ESP32 节点')
    box(s,610,330,365,175,'Broker','Mosquitto 消息服务器',cyan)
    box(s,1160,245,360,165,'订阅者 A','校验环境遥测')
    box(s,1160,505,360,165,'订阅者 B','接收状态与事件')
    s.arrow(435,418,590,418)
    s.text('发布',460,355,140,30,blue,True)
    s.line(990,418,1085,418,blue,5);s.line(1085,328,1085,588,blue,5)
    s.arrow(1085,328,1140,328);s.arrow(1085,588,1140,588)
    s.text('按主题转发',980,690,500,29,blue,True)
    s.text('Topic 示例：xiaoxi/dorm/node01/telemetry',80,606,970,30,font='Arial')
    band(s,'Wi-Fi：连接网络      TCP / TLS：建立加密连接      MQTT：按主题分发 JSON 消息')

    s=add('MQTT 在项目里的实际走向',50,
        '环境数据每10秒从node01发到原始遥测主题，校验器检查字段、来源和样本顺序，再发到validated主题，Home Assistant订阅这个主题更新实体。主题也区分不同用途：telemetry装温湿度和光照，status表示在线状态，event传按钮和红外事件，command发给红外节点。周期遥测采用QoS零，发送后不等待确认，下一轮继续上报新采样；在线状态采用QoS一并保留最近一条，用遗嘱消息通知意外断线。35秒没有新遥测时，HA把传感器标为不可用。',
        ['原始遥测 → 校验 → validated 主题 → HA 实体','telemetry / status / event / command 分工','10 s 上报，35 s 无更新后过期','status 保留最近状态，LWT 通知掉线'],['docs/mqtt-protocol.md','services/bridge/validator.py','home-assistant/mqtt/real/node01.yaml'])
    s.head('环境数据先校验再入库，状态、事件与命令各走自己的主题。')
    for i,(title,body) in enumerate([('node01','JSON 遥测'),('Broker','原始主题'),('validator','字段 / 来源 / 序号'),('Home Assistant','校验主题 → 实体')]):
        x=80+i*380;box(s,x,250,300,145,title,body,blue if i%2==0 else cyan,32)
        if i<3:s.arrow(x+310,322,x+365,322)
    s.text('原始：xiaoxi/dorm/node01/telemetry',90,437,1400,29,font='Arial')
    s.text('校验：xiaoxi/validated/node01/telemetry',90,483,1400,29,font='Arial')
    for x,a,b in [(90,'telemetry','环境值 · 每 10 s'),(470,'status','在线 / 离线 · retained'),(850,'event','按钮 / 红外事件'),(1230,'command','发给 node02')]:
        s.text(a,x,573,300,34,blue,True,font='Arial');s.text(b,x,630,310,26)
    band(s,'遥测：QoS 0 / 不保留      状态：QoS 1 / 保留 + LWT      TLS：8883      HA 过期：35 s')

    s=add('96 个像素，把状态显示出来',50,
        '这是UNO板上的12乘8点阵。正常情况下，表情、温度、湿度和亮度四幕轮播，每幕6秒；光照低于0.10时，多一幕困倦表情。笑脸里还藏了眨眼和爱心。这里直接用固件生成的像素帧来演示，数值输入是24度、55%湿度和46%相对亮度。PPT里嵌入了轮播动画，网页里还能单独选择状态、暂停和逐帧查看。',
        ['表情 → 温度 → 湿度 → 亮度','每幕 6 秒，暗光时增加困倦','示例输入：24℃ / 55%RH / 46%'],['firmware/arduino-uno-r4/include/led_companion.h'])
    s.head('表情、温度、湿度、亮度轮播；暗下来，再多一幕困倦。')
    s.matrix('happy',80,252,810,live='main')
    s.text('6 秒 / 幕',1010,278,500,76,blue,True)
    s.text('笑脸与爱心\n温湿度数字\n相对亮度\n暗光困倦',1020,408,480,38,ink,True)
    s.text('固件像素帧 · 数值为示例',1020,681,480,25,quiet)
    s.text('正常四幕；光照 < 0.10\n增加困倦第五幕。',1020,738,480,26,blue)

    s=add('从表情里，看出当前状态',30,
        '点阵也承担状态提示。语音交互时显示跳动声波，传感器异常时显示哭脸，联网时显示搜索表情。温度达到29度或者湿度达到75%时，第一幕会变成流汗脸。几种状态同时出现时，按语音、传感故障、网络连接、正常轮播的顺序显示。这样不用先打开电脑，也能看到节点正在做什么。',
        ['语音、故障、连接都有对应表情','温度 ≥ 29℃ 或湿度 ≥ 75%：流汗首幕','优先级：语音 → 传感故障 → 连接 → 轮播'],['firmware/arduino-uno-r4/include/led_companion.h'])
    s.head('交互、联网、传感异常，都有直观的点阵提示。')
    for x,key,label,desc in [(80,'voice','语音交互','预置声波动画'),(460,'cry','传感故障','哭脸提示'),(840,'connecting','正在连接','搜索表情'),(1220,'hot','高温 / 高湿','首幕显示流汗')]:
        s.matrix(key,x,318,300,live=key);s.text(label,x,580,310,36,ink,True);s.text(desc,x,643,310,28,quiet)
    band(s,'显示优先级：语音交互 → 传感器故障 → 网络连接 → 正常轮播')

    s=add('说一句话，交小西怎样找到答案',65,
        '以“现在宿舍温湿度怎么样”为例。浏览器录音后，先通过转写接口得到文字，再交给Hermes组织对话并请求大模型。模型根据问题发起ha_get_state调用，Hermes执行工具，经只读网关向Home Assistant读取温度和湿度实体。读数以结构化结果返回模型，模型再组织成自然语言回答，网页显示文字，并通过Edge TTS播报。所以模型负责理解和表达，具体数值由工具从传感系统里取。实体按钮也接入这个入口：按住开始录音，松手结束并发送。',
        ['浏览器语音 → 转写 → Hermes / LLM','LLM 发起 ha_get_state，Hermes 执行工具','只读网关查询 HA，数据返回模型','文字回答 + Edge TTS 语音播报'],['hermes/patches/hermes.patch','hermes/workspace/AGENTS.md','services/bridge/read_gateway.py'])
    s.head('理解问题 → 调用工具读取数据 → 组织回答 → 播报。')
    nodes=[('浏览器语音','录音 / 实体按钮'),('语音转文字','转写接口'),('Hermes + LLM','理解 / 发起调用'),('ha_get_state','Hermes 执行'),('只读网关 + HA','读取指定环境实体')]
    for i,(a,b) in enumerate(nodes):
        x=80+i*300;box(s,x,260,250,165,a,b,blue if i!=2 else cyan,29)
        if i<4:s.arrow(x+256,342,x+290,342)
    s.line(1405,430,1405,550,blue,5);s.line(1405,550,805,550,blue,5);s.arrow(805,550,805,438)
    s.text('温度 / 湿度 / 光照等结构化结果返回模型',870,491,640,27,blue,True)
    s.arrow(805,552,805,620)
    box(s,590,635,430,112,'文字回答 + Edge TTS','',cyan,32)
    s.text('模型据查询结果生成回答',1060,671,460,28,ink,True)
    s.text('按钮：按住录音，松手发送。示例问题：“现在宿舍温湿度怎么样？”',90,787,1430,29)

    s=add('工具怎样读到宿舍的实时数据',35,
        '工具读取的是HA中的五个实体：温度、湿度、相对光照、按钮事件和红外事件。模型按问题选需要的实体，比如问温湿度就读取两项。只读网关接收GET请求，附加后端凭据后查询HA，再把允许的状态字段返回Hermes。这样大模型可以查数据，而后端账户和设备控制留在平台侧。红外学习则使用独立的三个学习工具。',
        ['ha_get_state 按实体查询','只读网关开放五类实体','环境读取与红外学习分开提供工具'],['services/bridge/read_gateway.py','hermes/workspace/AGENTS.md','hermes/plugins/xiaoxi_ir_learning/__init__.py'])
    s.head('把问题对应到具体实体，再通过只读接口获取状态。')
    box(s,80,268,350,168,'Hermes 工具','ha_get_state')
    box(s,620,268,360,168,'只读网关','GET /api/states/实体 ID',cyan)
    box(s,1170,268,350,168,'Home Assistant','实体状态与属性')
    s.arrow(445,353,600,353);s.arrow(995,353,1150,353)
    for i,t in enumerate(['温度','湿度','相对光照','按钮事件','红外事件']):
        x=80+i*300;s.rect(x,538,240,86,pale);s.text(t,x+14,559,212,32,blue,True,align='center')
    s.text('查询示例：sensor.xiaoxi_node01_temperature',90,680,1430,30,font='Arial')
    s.text('工具读取当前状态；HA 在 35 秒无新遥测后更新为 unavailable。',90,761,1430,29,quiet)

    s=add('保留一天历史，平滑采样抖动',45,
        '平台保留最近24小时环境历史，每5分钟清理一次旧数据。分析端对温度、湿度和光照分别进行一维卡尔曼滤波：根据实际采样间隔更新估计，再结合新观测平滑瞬时抖动。图中用一组合成数据演示这个过程。设备重启或间隔超过35秒时重新初始化，保持估计和当前采样状态对应。',
        ['24 h 历史窗口，每 5 min 清理','温度、湿度、光照分别做一维卡尔曼','按实际采样间隔更新，重启和断流后重置'],['analytics/src/environment.py','home-assistant/automations/environment-retention.yaml','docs/history-and-kalman.md'])
    s.head('三路独立的一维卡尔曼，让趋势更容易看清。')
    import math
    values=[24+.28*math.sin(i*.21)+.16*math.sin(i*2.4)+(.6 if i==22 else 0) for i in range(60)]
    estimate=values[0];variance=.04;smooth=[]
    for v in values:
        variance+=.001;k=variance/(variance+.04);estimate+=k*(v-estimate);variance*=1-k;smooth.append(estimate)
    s.line(110,606,1020,606,quiet,3);s.line(110,315,110,606,quiet,3)
    for vals,c,width in [(values,'AAB8C2',3),(smooth,blue,6)]:
        pts=[(125+i*14.7,475-(v-24)*145) for i,v in enumerate(vals)]
        for a,b in zip(pts,pts[1:]):s.line(*a,*b,c,width)
    s.text('原始观测',110,246,250,29,quiet);s.line(280,269,345,269,'AAB8C2',4)
    s.text('平滑结果',415,246,250,29,blue);s.line(590,269,655,269,blue,5)
    s.text('时间 →',880,635,180,25,quiet)
    s.text('合成数据 · 滤波过程示意',110,720,900,26,quiet)
    s.text('24 小时',1120,284,400,58,blue,True)
    s.text('最近环境历史',1125,372,390,32)
    s.text('P⁻ = P + qΔt',1120,476,400,34,font='Arial')
    s.text('估计 + 新观测\n按不确定度加权',1125,551,390,31)

    s=add('空调红外：从原始波形开始学习',50,
        '红外部分遇到的问题是，原装遥控器的长帧与标准库默认发送的短帧不同。我们转向采集原始微秒时序，保留完整长帧。这个案例有280项时序，导出容量扩展到300项。操作上先建立基线，再逐键学习，用14个状态字段比较按键前后的变化。需要回放时，本地操作者完成prepare和commit，节点在38千赫载波上发送一次，现场观察空调响应。',
        ['280 项长帧案例，原始时序导出上限 300 项','基线 → 逐键学习 → 14 字段比对','prepare / commit 完成一次回放'],['docs/ac-onboarding.md','services/ir_learning/server.py','firmware/esp32-c3-ir/include/ir_raw_timing.h'])
    s.head('保存微秒时序，逐键录制，再对比状态变化。')
    s.text('280',90,250,440,128,blue,True,font='Arial');s.text('/ 300 项',510,289,740,75,ink,True)
    s.text('遥控器长帧案例 / 原始时序导出上限',95,427,1400,32)
    for i,(a,b) in enumerate([('建立基线','录入当前遥控状态'),('逐键学习','电源 / 模式 / 温度等'),('状态比对','14 个标准字段'),('一次回放','38 kHz · 挑战确认')]):
        x=80+i*380;box(s,x,545,300,145,a,b,blue if i%2==0 else cyan,32)
        if i<3:s.arrow(x+307,617,x+365,617)
    band(s,'Hermes 引导学习；本地操作确认回放，随后观察空调的实际响应。')

    s=add('三处联调，真正把器件接起来',40,
        '联调中有三处比较典型。第一，手上的SHT31是UART输出模块，我们实现字节流分帧和重同步。第二，UNO的点阵刷新会影响模拟引脚配置，采样前短暂消隐，稳定后读取A0，再恢复引脚访问。第三，C3的红外接收中断会打扰发送，所以发送期间暂停接收，再恢复。解决这些问题，让我们从能读到一个数，走到多个器件能够一起工作。',
        ['UART 字节流：分帧、校验、重同步','A0 与点阵：消隐后采样，恢复引脚访问','C3 红外：发射期间暂停接收中断'],['docs/hardware.md','docs/ac-onboarding.md','firmware/arduino-uno-r4/src/main.cpp','firmware/esp32-c3-ir/src/main.cpp'])
    s.head('串口分帧、引脚配置和中断时序，都在联调中逐一处理。')
    for y,label,cause,fix in [(275,'UART','传感模块输出字节流','按协议分帧，校验后重同步'),(445,'A0 / LED','点阵刷新影响模拟采样','短暂消隐，稳定后读数并恢复引脚访问'),(615,'IR 时序','接收中断影响发射波形','发送期间暂停接收，再恢复')]:
        s.text(label,90,y,320,51,blue,True,font='Arial')
        s.text(cause,470,y+3,1050,36,ink,True);s.text(fix,470,y+65,1050,30,quiet)

    s=add('五项新增采购，共 57.64 元',25,
        '这次新增采购五项，共57.64元，占200元预算的28.8%。包括温湿度模块、ESP32-C3、电阻包，以及红外接收和发射器。UNO、光敏模块、按钮和面包板沿用已有器件。把这些器件复用起来，我们完成了感知、通信和交互的整体搭建。',
        ['五项新增采购 57.64 元','200 元预算使用 28.8%','UNO、光敏模块、按钮、面包板复用'],['docs/hardware.md','presentation/final-defense/src/public-data.json'])
    s.head('复用已有器件，把新增预算花在传感和红外上。')
    s.text('57.64',90,295,800,145,blue,True,font='Arial');s.text('元 · 新增采购',98,493,700,39,ink,True)
    s.rect(100,615,670,25,pale);s.rect(100,615,670*.2882,25,cyan)
    s.text('预算使用 28.8% · 余 142.36 元',100,673,730,31)
    for i,(name,cost) in enumerate(purchases):
        y=270+i*80;s.text(name,930,y,410,32);s.text(f'{cost:.2f} 元',1350,y,170,32,align='right')
    s.text('复用：UNO、LM393、按钮、面包板',930,730,590,26,quiet)

    s=add('六人三组，沿接口协同',20,
        '六位同学分成三组：感知与点阵、红外与通信、平台与智能体。三条线通过MQTT数据格式、实体接口和统一状态定义对接。我们先约定各模块收什么、发什么，再并行开发和联调。',
        ['感知与点阵','红外与通信','平台与智能体'],['presentation/final-defense/src/public-data.json'])
    s.head('先约定数据格式和接口，再并行开发、一起联调。')
    for i,(role,names,scope) in enumerate(zip(['感知与点阵','红外与通信','平台与智能体'],groups,['UNO / 传感器 / LED / 按钮','ESP32-C3 / 红外学习 / MQTT TLS','Home Assistant / 滤波 / Hermes'])):
        y=275+i*157;s.text(role,90,y,470,43,blue,True);s.text('  ·  '.join(names),610,y+1,900,40,ink,True);s.text(scope,610,y+65,900,29,quiet)
    band(s,'共同接口：MQTT 消息格式 · 节点状态 · Home Assistant 实体 · 智能体工具')

    s=add('实物演示：从遮光，到一句回答',240,
        '下面用四分钟走一遍。第一分钟，遮挡再移开光敏模块，观察读数和点阵变化，也展示温湿度数字。第二分钟，按住按钮提问“现在宿舍温湿度和光照怎么样”，松手发送，查看网页转写、工具调用和语音回答。后两分钟，展示已录入的遥控器按键与状态比对，确认一次回放并观察空调响应。演示前打开网页、允许麦克风，并准备好遥控器和目标空调。',
        ['1 min：遮光与点阵','1 min：按住提问、松手发送、查看工具与回答','2 min：学习记录、确认回放、观察空调'],['docs/experiments.md','docs/ac-onboarding.md','hermes/patches/hermes.patch'])
    s.head('感知反馈 → 语音查询 → 红外学习与回放。')
    for x,t,title,body in [(90,'1 min','遮挡光照','观察相对亮度\n查看点阵数字与表情'),(600,'1 min','语音查询','按住提问，松手发送\n展示工具读取与播报'),(1110,'2 min','红外学习','查看已录按键\n确认回放，观察空调')]:
        s.text(t,x,294,420,75,blue,True,font='Arial');s.text(title,x,438,420,42,ink,True);s.text(body,x,535,420,31)
    band(s,'演示准备：网页与麦克风就绪，节点在线，遥控器和空调准备好。')

    s=add('谢谢大家',15,
        '交小西把宿舍里的传感器、无线通信和自然语言交互接在一起。从采集一个读数，到点亮一个表情，再到一次有数据依据的回答，这就是我们的课程实践。谢谢各位老师，欢迎提问。',
        ['让感知看得见，让交流有依据','欢迎提问'],['README.md'],kind='closing')
    s.text('谢谢大家',820,400,730,120,blue,True,align='center')
    s.text('让感知看得见，让交流有依据',770,575,780,38,blue,True,align='center')
    s.text('2026 年 11 月 · 结题答辩',620,687,580,29)
    s.text('交小西六人组',1200,687,330,29)

    s=add('附录：关键参数速查',0,
        '这一页用于回答周期、阈值和接口方面的问题。点阵、按钮、上报和历史窗口参数，都可以在对应固件或配置中找到。',
        ['点阵 6 s / 幕','MQTT 10 s 上报，HA 35 s 过期','24 h 历史，每 5 min 清理'],['firmware/arduino-uno-r4/include/led_companion.h','docs/mqtt-protocol.md','docs/history-and-kalman.md'])
    s.head('周期、阈值和接口参数。')
    params=[('SHT31 UART','9600 baud · 约 1 Hz'),('点阵轮播','6 s / 幕 · 暗光 < 0.10'),('流汗首幕','温度 ≥ 29℃ 或湿度 ≥ 75%'),('按钮手势','长按 700 ms · 松手发送'),('MQTT / HA','10 s 上报 · 35 s 过期'),('历史窗口','24 h · 每 5 min 清理'),('IR 学习','38 kHz · 导出上限 300 项'),('回放挑战','prepare / commit · 10 s 有效')]
    for i,(a,b) in enumerate(params):
        x=90+(i//4)*760;y=260+(i%4)*125;s.text(a,x,y,680,31,blue,True);s.text(b,x,y+54,690,30)

    s=add('附录：源码与参考资料',0,
        '点阵来自原固件头文件，MQTT主题和可靠性参数见协议文档，工具读取与语音流程分别对应网关和Hermes补丁。商业音箱对比参考DuerOS官方智能家居接入文档。',
        ['点阵、MQTT、网关、语音均有源码入口','商业平台参考 DuerOS 官方接入文档'],['README.md','docs/mqtt-protocol.md','hermes/patches/hermes.patch'])
    s.head('需要进一步解释时，回到这些实现入口。')
    refs=[('点阵 / 按钮','firmware/arduino-uno-r4/include/led_companion.h'),('MQTT 协议','docs/mqtt-protocol.md'),('只读网关','services/bridge/read_gateway.py'),('语音 / LLM','hermes/patches/hermes.patch'),('红外学习','services/ir_learning/server.py'),('商业平台','DuerOS 官方 · 智能家居快速接入')]
    for i,(a,b) in enumerate(refs):
        y=260+i*82;s.text(a,90,y,330,31,blue,True);s.text(b,430,y+2,1090,28,font='Arial' if '/' in b else None)
    s.text('蓝色校级模板：用户提供的 2021simpleblue.pptx',90,783,1430,26,quiet)
