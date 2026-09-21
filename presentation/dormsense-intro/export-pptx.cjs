const pptxgen = require('../../.pptx-tools/node_modules/pptxgenjs');

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'XiaoXi DormSense course project';
pptx.subject = '交小西宿舍智能体项目规划介绍';
pptx.title = 'XiaoXi DormSense · 交小西宿舍智能体';
pptx.company = 'Independent student course project';
pptx.lang = 'zh-CN';
pptx.theme = {
  headFontFace: 'PingFang SC',
  bodyFontFace: 'PingFang SC',
  lang: 'zh-CN'
};
pptx.defineSlideMaster({
  title: 'LIGHT',
  background: { color: 'FAFAF8' },
  objects: [],
  slideNumber: { x: 12.2, y: 0.28, w: 0.65, h: 0.18, color: '737373', fontFace: 'JetBrains Mono', fontSize: 8, align: 'right', margin: 0 }
});

const W = 13.333;
const H = 7.5;
const PAPER = 'FAFAF8';
const INK = '0A0A0A';
const GREY1 = 'F0F0EE';
const GREY2 = 'D4D4D2';
const GREY3 = '737373';
const BLUE = '002FA7';
const BLUE2 = '5B7BFF';
const WHITE = 'FFFFFF';
const FONT = 'PingFang SC';
const MONO = 'JetBrains Mono';

function rect(slide, x, y, w, h, fill, line = fill, transparency = 0) {
  slide.addShape(pptx.ShapeType.rect, {
    x, y, w, h,
    fill: { color: fill, transparency },
    line: { color: line, transparency: line === fill ? 100 : 0, width: 0.6 }
  });
}
function line(slide, x, y, w, h, color = GREY2, width = 0.7, dash = 'solid') {
  slide.addShape(pptx.ShapeType.line, { x, y, w, h, line: { color, width, dashType: dash } });
}
function txt(slide, text, x, y, w, h, size, color = INK, opt = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: opt.fontFace || FONT,
    fontSize: size,
    color,
    bold: !!opt.bold,
    italic: !!opt.italic,
    breakLine: false,
    margin: opt.margin === undefined ? 0 : opt.margin,
    valign: opt.valign || 'mid',
    align: opt.align || 'left',
    fit: opt.fit || 'shrink',
    charSpacing: opt.charSpacing,
    bullet: opt.bullet,
    paraSpaceAfterPt: opt.paraSpaceAfterPt,
    isTextBox: true
  });
}
function chrome(slide, left, index, dark = false, right) {
  const c = dark ? 'B8B8B8' : GREY3;
  txt(slide, left.toUpperCase(), 0.67, 0.35, 5.6, 0.18, 8, c, { fontFace: MONO, charSpacing: 2.1 });
  txt(slide, right || `${String(index).padStart(2, '0')} / 12`, 10.65, 0.35, 2.0, 0.18, 8, c, { fontFace: MONO, charSpacing: 2.1, align: 'right' });
}
function heading(slide, kicker, title, dark = false, size = 31) {
  txt(slide, kicker, 0.67, 0.78, 8.0, 0.22, 9, dark ? '9C9C9C' : GREY3, { charSpacing: 1.3 });
  txt(slide, title, 0.67, 1.02, 11.7, 0.62, size, dark ? PAPER : INK, { fit: 'shrink' });
}
function footer(slide, text, dark = false) {
  txt(slide, text, 0.67, 7.12, 11.9, 0.15, 7.5, dark ? '9C9C9C' : GREY3, { fontFace: MONO, charSpacing: 1.2 });
}
function note(slide, title, lines) {
  slide.addNotes(`${title}\n\n${lines.map(x => `• ${x}`).join('\n')}`);
}
function addBulletList(slide, items, x, y, w, dark = false, accent = false) {
  items.forEach((item, i) => {
    txt(slide, '—', x, y + i * 0.31, 0.22, 0.22, 9, accent ? BLUE : (dark ? PAPER : GREY3), { fontFace: MONO });
    txt(slide, item, x + 0.27, y + i * 0.31, w - 0.27, 0.24, 11, dark ? PAPER : INK);
  });
}

// 01 · Cover
{
  const s = pptx.addSlide();
  s.background = { color: BLUE };
  chrome(s, 'XiaoXi DormSense · Project Introduction', 1, true, 'SWISS · IKB · 01 / 12');
  txt(s, 'WIRELESS SENSOR NETWORK × AGENT', 0.67, 0.82, 7.2, 0.22, 9, 'D6DDF4', { fontFace: MONO, charSpacing: 2.3 });
  txt(s, '交小西', 0.67, 2.18, 6.1, 0.78, 52, WHITE);
  txt(s, '宿舍智能体', 0.67, 2.9, 7.4, 0.85, 55, WHITE, { italic: true });
  line(s, 0.67, 6.28, 12.0, 0, '6D82C5', 0.7);
  txt(s, '从宿舍微环境感知出发，规划一条可解释、可扩展、有安全边界的自然语言交互链路。', 0.67, 6.45, 8.0, 0.38, 14, 'E4E8F4');
  txt(s, '本科课程项目 · 规划介绍 · UNDER DEVELOPMENT', 0.67, 6.93, 6.2, 0.18, 8, 'AAB7DE', { fontFace: MONO, charSpacing: 1.8 });
  txt(s, '→ SWIPE / ARROW KEYS', 9.6, 6.93, 3.0, 0.18, 8, 'AAB7DE', { fontFace: MONO, charSpacing: 1.8, align: 'right' });
  note(s, '交小西宿舍智能体', ['项目从宿舍微环境这个具体问题出发', '融合无线传感网络、大数据基础与 Agent', '当前是规划介绍，不是已完成产品']);
}

// 02 · Forecast gap
{
  const s = pptx.addSlide('LIGHT');
  chrome(s, 'Context · The Gap', 2);
  heading(s, '天气没有错，尺度不同', '预报到不了床边');
  line(s, 6.66, 2.2, 0, 4.36, GREY2, 0.7);
  txt(s, 'A  CITY FORECAST', 0.72, 2.08, 4.8, 0.25, 9, GREY3, { fontFace: MONO, charSpacing: 1.7 });
  txt(s, '城市尺度', 0.72, 2.42, 4.8, 0.45, 23, INK);
  txt(s, '告诉我们一座城市大致的冷暖、降水与风，却无法代表一间宿舍此刻的闷热与潮湿。', 0.72, 2.93, 5.1, 0.62, 13, INK);
  line(s, 0.72, 5.78, 5.4, 0, GREY2);
  addBulletList(s, ['覆盖范围大', '刷新节奏统一', '难以反映室内局部差异'], 0.72, 5.96, 5.1);
  txt(s, 'B  DORM MICROCLIMATE', 7.18, 2.08, 4.8, 0.25, 9, BLUE, { fontFace: MONO, charSpacing: 1.7 });
  txt(s, '床边尺度', 7.18, 2.42, 4.8, 0.45, 23, BLUE);
  txt(s, '真正影响体验的，是室内温湿度、光照和设备状态在具体位置与时刻的变化。', 7.18, 2.93, 5.1, 0.62, 13, INK);
  line(s, 7.18, 5.78, 5.4, 0, GREY2);
  addBulletList(s, ['就在宿舍内测量', '保留时间变化', '让状态可以被查询与解释'], 7.18, 5.96, 5.1, false, true);
  note(s, '预报到不了床边', ['天气预报解决城市尺度趋势', '宿舍体验还受到朝向、通风和设备发热影响', '项目补充室内微环境观测，而不是替代天气预报']);
}

// 03 · Origin
{
  const s = pptx.addSlide();
  s.background = { color: INK };
  chrome(s, 'Origin · Three Forces', 3, true);
  heading(s, '项目方向不是凭空出现', '三个经历，汇成一个方向', true, 30);
  rect(s, 0.67, 1.87, 3.75, 4.87, BLUE);
  txt(s, 'WHY THIS PROJECT', 0.92, 2.09, 3.0, 0.23, 8.5, WHITE, { fontFace: MONO, charSpacing: 2.0 });
  txt(s, '感知\n连接\n理解', 0.92, 5.25, 2.1, 1.15, 29, WHITE, { valign: 'bottom' });
  const cards = [
    ['01', '天气多变', '我们需要比城市预报更贴近宿舍内部的局部观测。'],
    ['02', '用过智能音箱', '小爱同学、小度让“自然语言调用能力”变成直观的产品经验。'],
    ['03', '课程需要落地', '无线传感网络负责连接，大数据基础负责让时间序列可追溯、可分析。']
  ];
  cards.forEach((c, i) => {
    const y = 1.87 + i * 1.65;
    rect(s, 4.62, y, 8.04, 1.48, GREY1);
    txt(s, c[0], 4.86, y + 0.22, 0.75, 0.47, 25, BLUE);
    txt(s, c[1], 5.58, y + 0.18, 6.45, 0.28, 15, INK, { bold: true });
    txt(s, c[2], 5.58, y + 0.49, 6.45, 0.52, 11.5, INK);
  });
  note(s, '三个经历，汇成一个方向', ['天气多变带来本地感知需求', '智能音箱提供自然语言交互的产品经验', '两门课程分别提供连接与数据分析方法']);
}

// 04 · Goals
{
  const s = pptx.addSlide('LIGHT');
  chrome(s, 'Scope · Four Promises', 4);
  heading(s, '先把范围说清楚', '我们想做什么');
  line(s, 0.67, 1.82, 12.0, 0, GREY2);
  const cols = [
    ['01 / SENSE', '温度\n湿度', '以已确认的真实传感器为准；型号和接线核实后再实现驱动。'],
    ['02 / STATE', '光照\n节点状态', '光照先作为归一化量，不冒充 lux；同时区分在线、离线与缺测。'],
    ['03 / ASK', '自然语言\n查询', '用户描述需求，Agent 从经审核的状态来源读取并解释，而不是编造答案。'],
    ['04 / PRIVACY', '声音设想\n暂不接入', '当前不采集、不保存声音或语音；任何声环境扩展都需另行隐私评审。']
  ];
  cols.forEach((c, i) => {
    const x = 0.67 + i * 3.0;
    if (i > 0) line(s, x - 0.18, 1.82, 0, 4.92, GREY2);
    txt(s, `— ${c[0]}`, x, 2.08, 2.65, 0.22, 8.5, GREY3, { fontFace: MONO, charSpacing: 1.6 });
    txt(s, c[1], x, 3.0, 2.52, 0.9, 22, INK);
    txt(s, c[2], x, 4.05, 2.52, 1.1, 11.5, GREY3, { valign: 'top' });
  });
  note(s, '我们想做什么', ['MVP 优先温湿度和可靠状态', '光照不冒充 lux', '自然语言必须回到真实状态来源', '声音当前不采集、不保存']);
}

// 05 · System chain
{
  const s = pptx.addSlide('LIGHT');
  chrome(s, 'Architecture · Main Chain', 5);
  heading(s, '一条主链，两个安全边界', '数据怎样走到一句回答');
  const nodes = [
    ['01 · SENSE', '环境与传感器'], ['02 · EDGE', 'UNO R4 WiFi'], ['03 · TRANSPORT', 'Wi-Fi + MQTT'], ['04 · STATE', 'Home Assistant'], ['05 · AGENT', 'Hermes Agent']
  ];
  line(s, 1.25, 4.12, 10.8, 0, GREY2, 1.2);
  nodes.forEach((n, i) => {
    const x = 1.25 + i * 2.7;
    s.addShape(pptx.ShapeType.ellipse, { x: x - 0.055, y: 4.065, w: 0.11, h: 0.11, fill: { color: i === 4 ? BLUE : INK }, line: { color: i === 4 ? BLUE : INK, transparency: 100 } });
    const top = i % 2 === 0;
    txt(s, n[0], x - 0.7, top ? 3.55 : 4.33, 1.4, 0.2, 8, i === 4 ? BLUE : GREY3, { fontFace: MONO, align: 'center', charSpacing: 1.0 });
    txt(s, n[1], x - 0.9, top ? 3.77 : 4.55, 1.8, 0.27, 11.5, i === 4 ? BLUE : INK, { align: 'center' });
  });
  footer(s, '分析：从 Broker 读取只读遥测镜像                                      控制：只允许经 Home Assistant · 当前默认关闭');
  note(s, '数据怎样走到一句回答', ['传感器数据进入 UNO R4 WiFi', '经 Wi-Fi/MQTT 到 Home Assistant', 'Hermes 负责自然语言交互', '分析只读，控制只经 HA 且当前关闭']);
}

// 06 · Node roles
{
  const s = pptx.addSlide();
  s.background = { color: INK };
  chrome(s, 'Architecture · Node Roles', 6, true);
  heading(s, '从课程概念映射到系统组件', '三类角色，各做一件事', true);
  const cards = [
    [GREY1, INK, 'LAYER 01 · MEASURE', '测量节点', '各类传感器对应不同物理量。当前受硬件条件限制，传感器以有线方式连接 Arduino。', 'INPUT · PHYSICAL SIGNAL'],
    [BLUE, WHITE, 'LAYER 02 · AGGREGATE', '汇聚节点', 'UNO R4 WiFi 定时采样、校验状态、组织 JSON，并通过 Wi-Fi/MQTT 发送。', 'EDGE · DETERMINISTIC'],
    [INK, WHITE, 'LAYER 03 · CONTROL', '控制节点', '电脑或 VPS 承载 Broker、Home Assistant、分析与 Agent；具体容器化方式仍待联调。', 'HOST · COMPUTE + ORCHESTRATION']
  ];
  cards.forEach((c, i) => {
    const x = 0.67 + i * 4.12;
    rect(s, x, 1.92, 3.72, 4.85, c[0], i === 2 ? '666666' : c[0]);
    txt(s, c[2], x + 0.24, 2.18, 3.2, 0.2, 8, i === 0 ? GREY3 : 'BFC8E0', { fontFace: MONO, charSpacing: 1.5 });
    txt(s, c[3], x + 0.24, 5.48, 3.1, 0.33, 16, c[1]);
    txt(s, c[4], x + 0.24, 5.87, 3.1, 0.59, 10.5, c[1], { valign: 'top' });
    line(s, x + 0.24, 6.48, 3.1, 0, i === 0 ? GREY2 : '6E7DB1');
    txt(s, c[5], x + 0.24, 6.55, 3.1, 0.17, 7.2, i === 0 ? GREY3 : 'BFC8E0', { fontFace: MONO, charSpacing: 1.2 });
  });
  note(s, '三类角色，各做一件事', ['传感器是测量节点', 'UNO R4 WiFi 是汇聚节点', '电脑或 VPS 是主要控制节点', '当前传感器仍以有线方式接入 Arduino']);
}

// 07 · Compute boundary
{
  const s = pptx.addSlide();
  rect(s, 0, 0, W / 2, H, BLUE);
  rect(s, W / 2, 0, W / 2, H, GREY1);
  txt(s, 'EDGE', 0.48, 0.35, 1.2, 0.2, 8, 'D6DDF4', { fontFace: MONO, charSpacing: 2 });
  txt(s, '07 / 12', 5.32, 0.35, 0.9, 0.2, 8, 'D6DDF4', { fontFace: MONO, align: 'right' });
  txt(s, 'HOST', 7.18, 0.35, 1.2, 0.2, 8, GREY3, { fontFace: MONO, charSpacing: 2 });
  txt(s, 'COMPUTE BOUNDARY', 10.3, 0.35, 2.35, 0.2, 8, GREY3, { fontFace: MONO, charSpacing: 1.7, align: 'right' });
  txt(s, 'ARDUINO', 0.48, 3.02, 1.8, 0.2, 8, 'D6DDF4', { fontFace: MONO, charSpacing: 2 });
  txt(s, '专心\n测量', 0.48, 3.35, 4.5, 1.35, 43, WHITE);
  txt(s, '采样 · 缺测 · 重连 · 序号', 0.48, 7.0, 4.2, 0.17, 8, 'C5CEE8', { fontFace: MONO, charSpacing: 1.4 });
  txt(s, 'PC / VPS', 7.18, 2.62, 1.8, 0.2, 8, GREY3, { fontFace: MONO, charSpacing: 2 });
  txt(s, '负责', 7.18, 2.95, 3.2, 0.56, 36, INK);
  txt(s, '理解', 7.18, 3.5, 3.2, 0.62, 39, BLUE, { italic: true });
  txt(s, '算力有限的边缘节点不运行复杂 Agent；主机负责状态管理、历史分析和自然语言交互。', 7.18, 4.28, 4.5, 0.77, 13, INK);
  txt(s, '不逐样本调用 LLM · 规则先行', 7.18, 7.0, 4.2, 0.17, 8, GREY3, { fontFace: MONO, charSpacing: 1.4 });
  note(s, 'Arduino 专心测量，主机负责理解', ['微控制器负责稳定采样与重连', '复杂状态、统计和语言交互放在主机侧', '阈值和拒绝逻辑优先由确定性程序处理']);
}

// 08 · Hermes
{
  const s = pptx.addSlide('LIGHT');
  chrome(s, 'Agent · Hermes', 8);
  heading(s, 'THE AGENT THAT GROWS WITH YOU', '为什么规划使用 Hermes Agent', false, 29);
  const cards = [
    ['01', '自然语言', '把“宿舍现在怎么样”转成状态查询与解释。'],
    ['02', '持久记忆', '官方定位强调跨会话记忆与随使用成长。'],
    ['03', 'Skills', '把可复用流程沉淀为技能，而不是每次重新描述。'],
    ['04', '多模型', '可连接不同模型提供方，选择适合任务的推理能力。'],
    ['05', '隔离运行', '官方提供多种 sandbox backend；本项目仍需独立验证部署。'],
    ['06', 'Home Assistant', '上游有 HA 工具，但读写同属一个工具集，不能天然视为只读。']
  ];
  cards.forEach((c, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.67 + col * 4.05;
    const y = 1.82 + row * 2.34;
    rect(s, x, y, 3.83, 2.18, i === 5 ? BLUE : GREY1);
    txt(s, c[1], x + 0.2, y + 0.16, 2.7, 0.28, 13, i === 5 ? WHITE : INK, { bold: true });
    txt(s, c[0], x + 3.12, y + 0.16, 0.48, 0.2, 8, i === 5 ? 'CCD5F3' : GREY3, { fontFace: MONO, align: 'right', charSpacing: 1.3 });
    txt(s, c[2], x + 0.2, y + 1.42, 3.32, 0.55, 10.5, i === 5 ? WHITE : INK, { valign: 'bottom' });
  });
  footer(s, 'SOURCES · HERMES-AGENT.NOUSRESEARCH.COM · NOUSRESEARCH/HERMES-AGENT OFFICIAL DOCS');
  note(s, '为什么规划使用 Hermes Agent', ['官方定位是“The Agent That Grows With You”', '价值在于自然语言、记忆、Skills、多模型与隔离运行', 'HA 查询和调用在同一工具集中，不能天然视为只读']);
}

// 09 · Loop
{
  const s = pptx.addSlide();
  s.background = { color: INK };
  chrome(s, 'Interaction · Controlled Loop', 9, true);
  heading(s, '不是“说一句就随便执行”', '先读状态，再解释；控制以后再开', true, 28);
  const steps = ['用户以自然语言提出问题', 'Agent 从 HA 读取当前状态', '解释数据、时效与不确定性', '未来经确认后调用低风险场景'];
  steps.forEach((t, i) => {
    const y = 2.0 + i * 1.13;
    line(s, 0.67, y, 4.7, 0, '363636');
    txt(s, `0${i + 1}`, 0.67, y + 0.32, 0.38, 0.22, 8, BLUE2, { fontFace: MONO });
    txt(s, t, 1.1, y + 0.27, 4.25, 0.32, 12.5, PAPER);
  });
  line(s, 0.67, 6.52, 4.7, 0, '363636');
  s.addShape(pptx.ShapeType.ellipse, { x: 7.52, y: 2.42, w: 3.55, h: 3.55, fill: { color: INK, transparency: 100 }, line: { color: BLUE2, width: 1.3 } });
  [['ASK', 8.65, 2.0], ['READ', 11.3, 4.1], ['EXPLAIN', 8.55, 6.18], ['CONFIRM', 6.0, 4.1]].forEach(a => txt(s, a[0], a[1], a[2], 1.2, 0.2, 8, PAPER, { fontFace: MONO, align: 'center', charSpacing: 1.5 }));
  [[9.23,2.33],[10.98,4.12],[9.23,5.88],[7.45,4.12]].forEach(p => s.addShape(pptx.ShapeType.ellipse, { x:p[0], y:p[1], w:0.14, h:0.14, fill:{color:BLUE2}, line:{color:BLUE2,transparency:100} }));
  txt(s, 'LOOP', 8.25, 3.85, 2.1, 0.5, 30, PAPER, { align: 'center' });
  txt(s, 'READ · EXPLAIN · CONFIRM', 7.85, 4.36, 2.9, 0.2, 7.5, 'B8B8B8', { fontFace: MONO, align: 'center', charSpacing: 1.1 });
  note(s, '先读状态，再解释；控制以后再开', ['用户先提出问题', 'Agent 读取 HA 状态并说明时效', '先给解释与建议', '未来控制必须经过确认和状态回读']);
}

// 10 · Status
{
  const s = pptx.addSlide('LIGHT');
  chrome(s, 'Status · Evidence First', 10);
  heading(s, '规划介绍最重要的是不把未来写成现在', '已有骨架，不等于链路完成', false, 29);
  line(s, 6.66, 2.04, 0, 4.52, GREY2);
  txt(s, 'A  AVAILABLE NOW', 0.72, 1.96, 4.8, 0.25, 9, GREY3, { fontFace: MONO, charSpacing: 1.7 });
  txt(s, '工程骨架', 0.72, 2.29, 4.8, 0.44, 23, INK);
  txt(s, '协议、Schema、模拟器、Home Assistant 配置样例、部署说明与基础检查已经形成。', 0.72, 2.79, 5.1, 0.62, 13, INK);
  line(s, 0.72, 5.78, 5.4, 0, GREY2);
  addBulletList(s, ['UNO R4 WiFi 已确认', '模拟数据显式标记 simulated=true', '架构与安全边界已有文档'], 0.72, 5.96, 5.1);
  txt(s, 'B  NOT VERIFIED YET', 7.18, 1.96, 4.8, 0.25, 9, BLUE, { fontFace: MONO, charSpacing: 1.7 });
  txt(s, '真实验收', 7.18, 2.29, 4.8, 0.44, 23, BLUE);
  txt(s, '传感器型号、真实采样、MQTT/HA/Hermes 联调、设备控制与完整无线节点仍待现场验证。', 7.18, 2.79, 5.1, 0.68, 13, INK);
  line(s, 7.18, 5.78, 5.4, 0, GREY2);
  addBulletList(s, ['不虚构硬件测试结果', '不把静态配置说成已部署', '没有权限边界就不开控制'], 7.18, 5.96, 5.1, false, true);
  note(s, '已有骨架，不等于链路完成', ['已有协议、Schema、模拟器和配置样例', 'UNO R4 WiFi 已确认', '真实 MQTT、HA、Hermes 与硬件联调仍待完成', '没有证据的能力保持 Planned']);
}

// 11 · Roadmap
{
  const s = pptx.addSlide('LIGHT');
  s.background = { color: GREY1 };
  chrome(s, 'Roadmap · After The MVP', 11);
  heading(s, '先完成最小闭环，再扩展', '未来可以长成什么样');
  const cards = [
    ['01', 'TTS 输出', '让回答从屏幕文字扩展到可听见的反馈。'],
    ['02', '真正无线传感', '从有线传感器接入过渡到可扩展的无线节点。'],
    ['03', '更多物理量', '在型号、电气与隐私确认后增加新的测量通道。'],
    ['04', '历史分析', '清洗、窗口统计、趋势图与确定性异常检测。'],
    ['05', '安全控制', '仅通过 HA，经白名单、确认与状态回读后开放。'],
    ['06', '多节点扩展', '比较节点身份、可靠性、RSSI 与断线恢复。']
  ];
  cards.forEach((c, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.67 + col * 4.05;
    const y = 1.82 + row * 2.34;
    rect(s, x, y, 3.83, 2.18, i === 1 ? BLUE : PAPER);
    txt(s, c[1], x + 0.2, y + 0.16, 2.7, 0.28, 13, i === 1 ? WHITE : INK, { bold: true });
    txt(s, c[0], x + 3.12, y + 0.16, 0.48, 0.2, 8, i === 1 ? 'CCD5F3' : GREY3, { fontFace: MONO, align: 'right' });
    txt(s, c[2], x + 0.2, y + 1.42, 3.32, 0.55, 10.5, i === 1 ? WHITE : INK, { valign: 'bottom' });
  });
  note(s, '未来可以长成什么样', ['扩展 TTS、无线节点与更多物理量', '历史分析与异常检测对应课程目标', '控制只在 HA 路径和权限边界验证后开放']);
}

// 12 · Closing
{
  const s = pptx.addSlide();
  rect(s, 0, 0, W / 2, H, BLUE);
  rect(s, W / 2, 0, W / 2, H, PAPER);
  txt(s, '12 / 12', 0.48, 0.35, 1.2, 0.2, 8, 'D6DDF4', { fontFace: MONO });
  txt(s, 'CLOSING', 5.2, 0.35, 1.05, 0.2, 8, 'D6DDF4', { fontFace: MONO, align: 'right', charSpacing: 1.8 });
  txt(s, 'TAKEAWAYS', 7.18, 0.35, 1.7, 0.2, 8, GREY3, { fontFace: MONO, charSpacing: 1.8 });
  txt(s, '03 RULES', 11.4, 0.35, 1.2, 0.2, 8, GREY3, { fontFace: MONO, align: 'right', charSpacing: 1.8 });
  txt(s, 'MANIFESTO', 0.48, 2.65, 1.8, 0.2, 8, 'D6DDF4', { fontFace: MONO, charSpacing: 2 });
  txt(s, '先感知。\n再理解。', 0.48, 3.02, 5.0, 1.2, 40, WHITE);
  txt(s, '把宿舍里真实发生的变化，变成有来源、有边界的回答。', 0.48, 4.42, 4.65, 0.58, 12.5, 'E2E7F5');
  line(s, 0.48, 6.93, 5.75, 0, '6D82C5');
  txt(s, 'XIAOXI DORMSENSE', 0.48, 7.03, 2.2, 0.16, 7.5, 'AAB7DE', { fontFace: MONO, charSpacing: 1.5 });
  txt(s, 'Q&A', 5.55, 7.03, 0.68, 0.16, 7.5, 'AAB7DE', { fontFace: MONO, align: 'right' });
  const rules = [
    ['01', '从真实问题出发', '天气预报提供城市尺度，项目补足宿舍微环境尺度。'],
    ['02', '让节点各司其职', 'Arduino 可靠采样，主机管理状态、分析与自然语言交互。'],
    ['03', '先验证，再扩展', '真实链路、权限边界和隐私审查通过后，再谈 TTS、无线节点与家居控制。']
  ];
  rules.forEach((r, i) => {
    const y = 2.42 + i * 1.38;
    line(s, 7.18, y, 5.42, 0, i === 2 ? BLUE : GREY2, i === 2 ? 1.2 : 0.7);
    txt(s, r[0], 7.18, y + 0.17, 0.82, 0.45, 27, i === 2 ? BLUE : INK);
    txt(s, r[1], 8.04, y + 0.13, 3.85, 0.28, 14, i === 2 ? BLUE : INK, { bold: true });
    txt(s, r[2], 8.04, y + 0.44, 4.45, 0.52, 10.5, GREY3);
  });
  line(s, 7.18, 6.56, 5.42, 0, BLUE, 1.2);
  txt(s, '→ 谢谢 · END OF INTRODUCTION', 9.25, 7.0, 3.35, 0.17, 7.5, GREY3, { fontFace: MONO, align: 'right', charSpacing: 1.2 });
  note(s, '先感知，再理解', ['从真实宿舍微环境问题出发', '让传感器、Arduino、平台和 Agent 各司其职', '先验证真实链路与边界，再扩展语音、无线和控制']);
}

pptx.writeFile({ fileName: 'presentation/dormsense-intro/XiaoXi-DormSense-项目介绍.pptx' });
