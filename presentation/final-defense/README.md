# 交小西 DormSense 结题答辩

本版使用用户指定的 [2021simpleblue 模板](./assets/2021simpleblue.pptx)，沿用校徽、校园照片、蓝色切面、目录和正文标题标识。共 18 页主线、2 页答疑附录，建议讲解与演示合计 14 分 15 秒，其中实物演示 4 分钟，另留 45 秒切换缓冲。

## 直接打开

- [可编辑 PowerPoint](./交小西DormSense_结题答辩展示.pptx)：正文、表格和流程图由可编辑对象组成；第 8 页嵌入 LED 状态动画，所有页面附有演讲者备注。
- [PDF 预览](./交小西DormSense_结题答辩展示.pdf)：完整固定版式，适合快速查看和备用投影。
- [逐页讲稿](./逐页讲稿.md)：与 PPT 标题、顺序、备注和计时一致。
- [全部页面总览](./previews/全部页面总览.png) 与 [重点页面](./previews/精选页面.png)：集中查看新增的对比、MQTT、点阵和实际流程。
- [离线网页](./index.html)：直接打开即可翻页；方向键或空格前进，N 打开讲稿。第 8 页提供九类点阵状态、暂停和逐帧操作。
- [LED 状态动画](./assets/LED_五种状态演示.gif)：30 秒循环展示表情、温度、湿度、亮度和困倦。

## 本版内容

第 4 页比较交小西与小度等商业智能音箱的使用定位、设备接入和开发方式；商业平台资料来自 DuerOS 官方文档。

第 6 页介绍 MQTT 的发布者、Broker、订阅者和 Topic，第 7 页对应项目实际主题、数据校验、QoS、保留状态、LWT 和过期设置。图中把 Wi-Fi 网络接入、TCP / TLS 连接与 MQTT 消息分发分别讲清楚。

第 10 页展示语音输入、文字转写、Hermes 与大模型、`ha_get_state` 调用、只读网关与 HA 查询、数据返回模型、文字与语音回答的完整过程。第 11 页进一步解释实体与只读接口的关系。

点阵帧直接由 [固件头文件](../../firmware/arduino-uno-r4/include/led_companion.h) 生成。24℃、55%RH、46% 是展示输入，困倦用 4% 暗光；第 12 页滤波曲线标注为合成数据示意。五项新增采购共 57.64 元，UNO 等已有器件复用。

## 修改与导出

[文案与布局](./src/content.py) 集中定义逐页内容，[生成器](./src/build.py) 输出 PPTX、HTML、SVG、备注、讲稿和点阵素材；[导出程序](./src/export.py) 生成 PDF、逐页 PNG 和页面总览。成员与采购金额保存在 [公开元数据](./src/public-data.json)。

在仓库根目录运行：

```bash
.venv/bin/python presentation/final-defense/src/build.py
.venv/bin/python presentation/final-defense/src/export.py
```

生成环境使用 Python 的 python-pptx、Pillow、clang++、LibreOffice、Poppler，以及已安装的微软雅黑；英文和数值使用 Arial。PDF 用于保持固定外观。检查记录与素材来源见 [制作与验收说明](./验收说明.md)。
