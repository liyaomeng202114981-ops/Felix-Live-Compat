# 从零安装

目标环境是 Ubuntu 26.04 x86-64、GNOME Wayland、XWayland、PipeWire 和 Vulkan。采集需要一个可确定的 DRM render node。运行还需要 systemd 用户服务、Steam Linux Runtime 4、`python3-gi`、`python3-xlib`、`gir1.2-atspi-2.0`、`tar` 和 `zstd`。

## 构建兼容包

构建环境需要 Docker、`patch`、`python3-pefile`、C 编译器、`pkg-config`、`libpipewire-0.3-dev`、`libspa-0.2-dev`、`libdrm-dev`、`libvulkan-dev` 和 `glslang-tools`。固定的 SteamRT4 SDK 同时用来构建 WGC 组件与 Wine 的 IPC 和 XWayland 模块。在源码目录执行：

```bash
sdk=registry.gitlab.steamos.cloud/proton/steamrt4/sdk/x86_64@sha256:6c1789cad862fd8ed9d46d71bbf8752bb7cb2336ab5e9680c0f0e3e7c88d77f1
docker pull "$sdk"
/usr/bin/python3 -B tools/build_package.py --output dist/felix-live-compat-local.tar.gz
mkdir -p build/unpacked
tar -xf dist/felix-live-compat-local.tar.gz -C build/unpacked
cd build/unpacked/Felix-Live-Compat
```

构建和安装都可以用 `--assets DIR` 读取缓存中的上游依赖，两条命令均核对 [assets.json](../assets.json) 的 SHA-256。使用解包的 Ubuntu 开发头文件时，构建额外接受 `--sysroot DIR`，可用 `GLSLANG_VALIDATOR` 指定编译器。

## 安装与启动

下载官方 Windows x64 安装器。把 `installer` 指向该文件，把 `target` 指向尚不存在的目录。工具先检查 systemd 用户服务、Wayland/XWayland、PipeWire、ScreenCast Portal 和 GPU 依赖，再初始化新前缀。安装器需要交互时可加 `--interactive`，沿用官方默认安装位置。[官方下载](https://streamingtool.douyin.com/)

```bash
installer="$HOME/Downloads/StreamingTool-x64.exe"
target="$HOME/Games/Felix-Live-Compat"
/usr/bin/python3 -B tools/felix_live.py preflight
/usr/bin/python3 -B tools/felix_live.py install --root "$target" --installer "$installer"
```

安装完成后，在 GNOME 应用列表点击「直播伴侣（Felix 兼容版）」，也可从右键菜单将它添加到 Dock。入口使用该安装目录的启动程序和直连选项，解包目录可以移走。终端启动时可用下列命令。客户端可能先更新或要求扫码。进入主界面后，从「添加素材」选「全屏」或「窗口」，再在 Ubuntu 系统选择器授权。声音默认使用当前会话的音频设备。

```bash
/usr/bin/python3 -B "$target/launcher/tools/felix_live.py" launch --root "$target" --direct
```

平时用伴侣菜单退出。如果客户端卡住，可以在兼容版 Dock 图标右键点「强制退出（Felix 兼容版）」。该操作停止本次安装的用户服务，必要时在 5 秒后终止同一服务组的剩余进程。它会中断该实例正在录制或推送的内容。应用 ID 和服务名均由安装目录生成，每个前缀有自己的入口。[桌面动作规范](https://specifications.freedesktop.org/desktop-entry/latest/extra-actions.html)

启用 Ubuntu AppIndicator 扩展的 GNOME 会话还会在顶栏显示兼容版的摄像机图标。右键菜单中的「强制退出（Felix 兼容版）」同样只停止这个安装的服务。服务结束后图标自动消失。托盘使用 `StatusNotifierItem` 和 `DBusMenu`，由系统桌面呈现。系统未启用托盘扩展时仍可使用 Dock 入口。[Ubuntu AppIndicator 扩展](https://github.com/ubuntu/gnome-shell-extension-appindicator)

伴侣注册自己的托盘后，摄像机图标还会显示「打开直播伴侣」「重置直播伴侣窗口」和「退出直播伴侣」。这些动作调用同一实例的原托盘，正常退出保留伴侣的确认框。「直播伴侣原菜单…」可以直接打开应用自己的菜单。遇到原菜单文本变化时也可以在打开的原菜单里选择。

使用自有动态图时可运行 `GDK_BACKEND=wayland /usr/bin/python3 -B tools/test_source.py`，需要 `gir1.2-gtk-4.0` 和 `python3-gi-cairo`。可通过伴侣的本地录制核验画面与声音。[从零安装验收](CLEAN_INSTALL_TEST.md)
