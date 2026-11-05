# XiaoXi 品牌资源模板

终端采用单行小写 `xiaoxi`，网页采用团队提供的项目 Logo。终端皮肤见[皮肤模板](../skins/xiaoxi.yaml)，安装与恢复见[皮肤说明](../skins/README.md)。

网页资源来自现有的[团队项目图](../../presentation/dormsense-intro/images/xiaoxi-dormsense-logo.png)，保留比例与透明通道，不裁切、不重新绘制形象。它是课程项目素材，不表示学校或相关形象的官方授权。[资源清单](manifest.json)记录输入、Pillow 版本、尺寸和每个文件的 SHA-256。

| 资源 | 用途 |
| --- | --- |
| [xiaoxi-logo.png](xiaoxi-logo.png) | 网页侧栏和移动端顶栏，512 × 512 |
| [xiaoxi-login.png](xiaoxi-login.png) | 登录页内嵌图像，192 × 192 |
| [favicon.ico](favicon.ico) | 浏览器页签，包含 16–256 像素的真实 ICO 图像 |
| [apple-touch-icon.png](apple-touch-icon.png) | 180 × 180 的可复用收藏图标素材 |

[Dockerfile](../Dockerfile)把三张 PNG 放入 `web/public/ds-assets/`，把 ICO 放入 `web/public/favicon.ico`。Vite 构建复制到实际网页目录；侧栏使用现有 base-path helper，登录页把本地公共 PNG 编码成 data URL，不新增登录前的资源放行规则。缺少图片时登录页退回 `xiaoxi` 字标，认证仍可正常加载。收藏图标素材已保存，当前没有新增 PWA 或桌面应用。

可复现的界面改动保存在[补丁](../patches/hermes.patch)和[源码哈希清单](../patches/manifest.json)，包括网页标题、移动/展开/折叠侧栏、页脚、登录页，以及经典 CLI 和 Ink TUI 的品牌文字。上游许可证、真实版本、模型与认证提供方标识继续保留。复用时替换图片与皮肤，并按清单核对后构建；不要用示例配置覆盖已有 profile。

当前原实例已安装简洁皮肤；网页和终端构建通过后发布到同一容器。浏览器缓存可能保留旧页签图标，刷新页面后若仍未更新可使用强制刷新。登录后的人工视觉验收与源文件/构建/HTTP 验证分别记录。
