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

下载官方 Windows x64 安装器。把 `installer` 指向该文件，把 `target` 指向尚不存在的目录。工具先在新运行器中安装配套的 Wine IPC 和 XWayland 模块，再执行官方安装器并为该前缀注册 WGC 和 D3D11 组件。安装器需要交互时可加 `--interactive`，沿用官方默认安装位置。[官方下载](https://streamingtool.douyin.com/)

```bash
installer="$HOME/Downloads/StreamingTool-x64.exe"
target="$HOME/Games/Felix-Live-Compat"
/usr/bin/python3 -B tools/felix_live.py install --root "$target" --installer "$installer"
/usr/bin/python3 -B tools/felix_live.py launch --root "$target"
```

官方客户端可能先更新或要求扫码。进入主界面后，从「添加素材」选「全屏」或「窗口」，再在 Ubuntu 系统选择器授权。声音默认使用当前会话的音频设备。需要伴侣专属直连时，在启动命令加 `--direct`。正常退出请用客户端菜单。也可停止这套独立服务：

```bash
/usr/bin/python3 -B tools/felix_live.py stop --root "$target"
```

使用自有动态图时可运行 `GDK_BACKEND=wayland /usr/bin/python3 -B tools/test_source.py`，需要 `gir1.2-gtk-4.0` 和 `python3-gi-cairo`。可通过伴侣的本地录制核验画面与声音。[从零安装验收](CLEAN_INSTALL_TEST.md)
