# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Check the dependencies used by the Wayland/XWayland compatibility session."""

import ctypes
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def check_dependencies():
    missing = []
    warnings = []
    if sys.platform != "linux" or platform.machine() != "x86_64":
        missing.append("本安装包需要 x86-64 Linux。")
    if sys.version_info < (3, 11):
        missing.append("需要 Python 3.11 或更新版本，请使用系统 /usr/bin/python3。")
    for command, package in {
        "bash": "bash", "tar": "tar", "zstd": "zstd", "sha256sum": "coreutils",
        "systemctl": "systemd", "systemd-run": "systemd",
    }.items():
        if not shutil.which(command):
            missing.append(f"缺少 {command}（Ubuntu 软件包 {package}）。")
    if not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
        missing.append("需要 cgroup v2，以隔离启动和退出。")
    if shutil.which("systemctl"):
        try:
            if subprocess.run(["systemctl", "--user", "show", "--property=Version", "--value"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=3).returncode:
                missing.append("无法连接 systemd 用户服务，请从当前桌面会话运行。")
        except subprocess.TimeoutExpired:
            missing.append("systemd 用户服务响应超时。")

    runtime = os.environ.get("XDG_RUNTIME_DIR")
    wayland = os.environ.get("WAYLAND_DISPLAY")
    if not runtime or not wayland or not (Path(runtime) / wayland).is_socket():
        missing.append("找不到 Wayland 会话，请从 Ubuntu Wayland 桌面运行。")
    if runtime:
        pipewire = os.environ.get("PIPEWIRE_RUNTIME_DIR") or runtime
        if not (Path(pipewire) / (os.environ.get("PIPEWIRE_REMOTE") or "pipewire-0")).is_socket():
            missing.append("找不到 PipeWire 套接字，请检查 pipewire 用户服务。")

    try:
        from Xlib import display, error
    except ImportError:
        missing.append("缺少 python3-xlib。")
    else:
        try:
            display.Display().close()
        except (OSError, error.DisplayError):
            missing.append("无法连接 DISPLAY，请确认当前会话启用了 XWayland。")

    try:
        import gi
        from gi.repository import Gio, GLib
    except ImportError:
        missing.append("缺少 python3-gi 或 GLib/Gio 的类型库。")
    else:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            variants, = bus.call_sync(
                "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", ("org.freedesktop.portal.ScreenCast", "AvailableSourceTypes")),
                GLib.VariantType.new("(v)"), Gio.DBusCallFlags.NONE, 3000, None,
            ).unpack()
            if variants & 3 != 3:
                missing.append("ScreenCast Portal 未同时提供显示器和窗口共享。")
        except GLib.Error:
            missing.append("ScreenCast Portal 无响应，请检查 xdg-desktop-portal 和 xdg-desktop-portal-gnome。")
        try:
            gi.require_version("Atspi", "2.0")
        except ValueError:
            warnings.append("缺少 gir1.2-atspi-2.0，窗口素材会使用通用名称。")

    for library, package in {
        "libpipewire-0.3.so.0": "libpipewire-0.3-0t64", "libdrm.so.2": "libdrm2",
        "libvulkan.so.1": "libvulkan1",
    }.items():
        try:
            ctypes.CDLL(library)
        except OSError:
            missing.append(f"无法加载 {library}（Ubuntu 软件包 {package}）。")
    nodes = list(Path("/dev/dri").glob("renderD*"))
    if len(nodes) != 1:
        missing.append(f"检测到 {len(nodes)} 个 DRM render node，当前采集需要一个。")
    elif not os.access(nodes[0], os.R_OK | os.W_OK):
        missing.append(f"当前用户无法读写 {nodes[0]}，请检查 GPU 设备权限。")

    if not (shutil.which("curl") or shutil.which("wget")):
        warnings.append("缺少 curl 或 wget，wrapper 可能无法下载 Steam Linux Runtime 4。")
    if os.environ.get("SHORIN_PROTON_WRAPPER_RUNTIME") == "0":
        warnings.append("环境已关闭 Steam Linux Runtime，正常安装和启动建议保持启用。")
    for message in warnings:
        print(message, file=sys.stderr)
    if missing:
        raise ValueError("依赖预检未通过\n" + "\n".join(f"- {item}" for item in missing))
    print("依赖预检通过。Steam Linux Runtime 4 由 wrapper 查找或下载。", flush=True)
