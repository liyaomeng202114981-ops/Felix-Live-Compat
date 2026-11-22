# 拖拽缩放辅助进程（ui_resize）

## 问题

Wine 里的官方 Windows 客户端在拖拽缩放时不做实时重排：一次重排约 40 ms（同步等待 19.1 ms、Reshape 11.3 ms、SwapBuffers 9.3 ms），而 60 Hz 的预算是 16.7 ms。结果是拖拽中内容追不上窗口，松手后画面才跳变。

## 做法

会话启动后，`tools/felix_live.py` 在客户端主窗就绪时拉起 `tools/ui_resize_preview.py`：

1. **抓手**：在客户端窗口上覆盖 9 个 `InputOnly` 子窗口（8 方向 + 顶部移动条），子窗口持有光标形状并 `grab_button`，不参与绘制、不影响应用自身控件；
2. **门控 resize**：拖拽期每 100 ms 最多发一条 `_NET_MOVERESIZE_WINDOW`，并且只有上一目标尺寸拿到有效帧才继续，避免请求堆积；
3. **预览层**：拖拽期用覆盖窗口显示一张冻结帧，按当前窗口尺寸等比拉伸，看起来连续；
4. **收尾**：松手后持续抓帧，直到「尺寸匹配 + 画面内容签名连续两帧一致」，再压 150 ms 撤掉覆盖层，保证交接时下面已经是重排完成的真实界面；
5. **兜底**：`_enforce_final()` 在松手 250 ms 后校验几何，被改回则补发最终矩形（最多 3 次）。

尺寸下限跟随应用自身（直播伴侣实测 1080×720），不再继承 WeGame 修复版里写死的 1280×720；客户端报告的实际尺寸会被采纳为新基准（`adopt`）。

## 边界

- 拖拽期的「流畅」是拉伸的一张图，不是实时重排——这是 Wine 下应用自身不重排决定的，任何外层方案都无法绕过；
- 仍未验证：真实开播场景（共享/录制/音画/长稳）；
- 抓手依赖 X11/XWayland 窗口语义；纯 Wayland 会话不在当前支持范围。

## 开关与日志

- `--no-ui-resize` 关闭；默认开启。
- 日志：`$XDG_RUNTIME_DIR/<unit>/ui-resize.log`，事件包括 `attach`/`layout`/`resize_start`/`resize_request`/`resize_end`/`final_settled`/`adopt`。
- 抓帧策略可切：环境变量 `FELIX_LIVE_FRAMES=1` 使用活帧（内容更新但缩放比≈1:1），默认冻结帧。

## 迁移说明

实现移植自本机 `wegame-window-fix`（纯 Python/Xlib，无注入、无 DLL）。相较原版改动：窗口身份匹配改为 `WM_CLASS` 含「直播伴侣」+ 可缩放主窗判定（`WM_NORMAL_HINTS` 无 max 尺寸、无 transient、`NORMAL` 类型）；抓帧允许 depth 32（ARGB）源；收尾判据从「尺寸稳定」升级为「画面内容稳定」。
