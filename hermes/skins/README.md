# XiaoXi 终端皮肤模板

[皮肤模板](xiaoxi.yaml)只显示一行小写 `xiaoxi`。上一版像素头像已退出当前模板；网页使用的项目图片单独保存在[品牌资源目录](../branding/README.md)。

模板使用原生 `branding.agent_name`、`banner_logo` 和 `banner_hero`。`banner_hero: " "` 特意保留一个空格，用来阻止原生头像回退。项目的 Ink 补丁将空头像切换为单栏会话信息，避免把真实模型、目录和会话挤入狭窄头像列；固定厂商标语和模型旁的公司后缀已移除。

## 安装与恢复

在选定 profile 中创建 `skins` 目录并放入模板，使用官方命令：

```bash
hermes skin use xiaoxi
# 恢复原生配色与皮肤选择：
hermes skin use default
```

当前容器的官方 profile 为 `/opt/data`，皮肤位置是 `/opt/data/skins/xiaoxi.yaml`，本实例操作用户为 `10000:10000`。项目镜像将公共模板置于 `/opt/xiaoxi/skins/xiaoxi.yaml`，构建镜像不会覆盖持久 profile。不要用示例配置替换用户配置。

皮肤选择控制原生名称与颜色；项目源码补丁负责简化终端布局和移除固定标语。选择 `default` 不会撤销源码补丁，若要完整恢复上游界面，应使用匹配的原始镜像并保留用户数据。

字标只有 6 个 ASCII 字符，不依赖像素头像分辨率。原生 Rich 模板加载已核对；修改后的 Ink 产物须经过独立终端构建，网页构建不会更新它。现有会话终端可能仍运行旧产物，刷新并打开新终端后核对外观。
