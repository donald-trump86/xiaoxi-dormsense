# 交小西终端皮肤模板（`hermes/skins`）

- [xiaoxi.yaml](xiaoxi.yaml)：CLI / TUI 共用的小写 `xiaoxi` 像素字标，宽 62 列、高 7 行，采用浅金到暖红的逐行渐变。可用宽度达到 64 列时展示完整横幅，较窄的终端保留简短文字标题。
- 由于 Hermes TUI 的 `parseRichMarkup()` 按单行色块解析，皮肤中的横幅每一物理行均使用单一 `[#RRGGBB]...[/]` 颜色标签包裹，确保在终端与 Web PTY 中对齐渲染。
- 通过 `hermes skin use xiaoxi` 或在 `config.yaml` 中设置 `display.skin: xiaoxi` 即可启用，用户也可复制到 `/opt/data/skins/` 下自行定制。
