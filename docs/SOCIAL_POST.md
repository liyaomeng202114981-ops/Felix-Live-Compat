# 自媒体图文素材

三张图片均为 **1440×1920（3:4）**，可直接保存发布，无需再截长页面。图中为原创实现示意，不是客户端截图。源码 SVG 与生成脚本一并公开，方便修改文字和重新导出。

**[一键下载三张竖图与发布文案（ZIP）](media/felix-live-compat-social-3x4.zip?raw=true)** · **[复制纯文本标题与正文](media/social-caption.txt)**

| 顺序 | 内容 | 高清图片 | 可编辑矢量 |
| --- | --- | --- | --- |
| 1 | 封面：Ubuntu 上使用直播伴侣 | [PNG](media/social-01-cover.png) | [SVG](media/social-01-cover.svg) |
| 2 | 已验证的采集、音画与短时开播 | [PNG](media/social-02-tested.png) | [SVG](media/social-02-tested.svg) |
| 3 | Linux 原生采集到官方客户端的流程 | [PNG](media/social-03-flow.png) | [SVG](media/social-03-flow.svg) |

## 标题

Ubuntu 上也能用抖音直播伴侣了：我的开源兼容项目

## 正文（可直接使用）

我把官方 Windows 版抖音直播伴侣接到了 Ubuntu：在伴侣里点全屏或窗口，选择 Ubuntu 允许共享的画面，就能进入预览和直播流程。这条采集链路不用采集卡，也不经过虚拟摄像头。

项目叫 **Felix Live Compat**，兼容层和安装工具已开源。已分阶段实测从零安装、桌面／多窗口采集、本地音画录制，以及隔离候选的短时全屏和窗口开播。

目前是预发行版，UI 缩放体验还在打磨；长时直播和观众端画质仍待验证。欢迎有相近环境的 Linux 用户试用、反馈问题。

GitHub：[liyaomeng202114981-ops/Felix-Live-Compat](https://github.com/liyaomeng202114981-ops/Felix-Live-Compat)

`#Linux` `#Ubuntu` `#开源项目` `#游戏直播` `#直播伴侣`

## 测试表述依据

图片上的“已实测”指仓库保留的分阶段历史结果，不表示最新包重复完成了全部测试。全屏／窗口和本地音画见[安装验收](CLEAN_INSTALL_TEST.md)，多窗口和清理见[选窗记录](streaming/WINDOW_PICKER_MULTI_WINDOW.md)及[清理记录](streaming/WINDOW_PICKER_CLEANUP.md)，短时推流见[短时实播记录](SHORT_LIVE_TEST.md)。

实测环境为 Ubuntu 26.04、GNOME Wayland／XWayland、NVIDIA RTX 4060；官方客户端构建号为 13.3.5.564315535。其他环境的兼容性、观众端画质与长时间稳定性尚待补充。项目为社区兼容方案，当前客户端 UI 通过 Wine／Proton 运行。

## 重新导出

在仓库根目录运行（需要系统的 GI／Rsvg／Cairo Python 绑定）：

```bash
/usr/bin/python3 -B tools/render_presentation.py
```

脚本不访问桌面、客户端、网络或账号信息，仅生成原创 SVG 和 PNG。仓库首页另外使用 `media/readme-hero.png` 与横版 `media/capture-flow.png`。
