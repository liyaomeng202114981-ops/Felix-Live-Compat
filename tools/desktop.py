# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Register one user-level desktop entry for an independent installation."""

import hashlib
import os
from pathlib import Path
import re
import tempfile


def instance_key(root):
    return hashlib.sha256(os.fsencode(root)).hexdigest()[:16]


def application_id(root):
    return f"io.github.felixli.LiveCompat.p{instance_key(root)}"


def desktop_path(root):
    from gi.repository import GLib

    return Path(GLib.get_user_data_dir()) / "applications" / f"{application_id(root)}.desktop"


def exec_line(*args):
    def quote(value):
        escaped = "".join("\\" + char if char in '\\"`$' else char for char in str(value))
        return '"' + escaped.replace("%", "%%") + '"'

    return " ".join(map(quote, args))


def companion_icon(root, launcher):
    versions = [
        directory for directory in launcher.parent.iterdir()
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", directory.name)
        and (directory / "直播伴侣.exe").is_file()
    ]
    versions.sort(key=lambda directory: tuple(map(int, directory.name.split("."))), reverse=True)
    source = next((directory / "icon.ico" for directory in versions
                   if (directory / "icon.ico").is_file()), None)
    if source is None:
        return "camera-video"

    import gi
    from gi.repository import GLib

    try:
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf

        icon = GdkPixbuf.Pixbuf.new_from_file_at_size(str(source), 256, 256)
        target = root / "launcher/companion-icon.png"
        icon.savev(str(target), "png", [], [])
    except (ImportError, ValueError, GLib.Error):
        return "camera-video"
    return str(target)


def register_desktop(root, launcher):
    from gi.repository import GLib

    target = desktop_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    script = root / "launcher/tools/felix_live.py"
    command = ("/usr/bin/python3", "-B", script)
    config = GLib.KeyFile()
    entry = "Desktop Entry"
    for name, value in {
        "Type": "Application",
        "Name": "Douyin Live Companion (Felix Compat)",
        "Icon": companion_icon(root, launcher),
        "Exec": exec_line(*command, "launch", "--root", root, "--direct"),
        "StartupWMClass": application_id(root),
        "Categories": "AudioVideo;Video;",
        "Keywords": "Felix Compat;Douyin;直播伴侣;兼容版;",
        "Actions": "ForceQuit;",
    }.items():
        config.set_string(entry, name, value)
    config.set_locale_string(entry, "Name", "zh_CN", "直播伴侣（Felix 兼容版）")
    config.set_boolean(entry, "Terminal", False)
    config.set_boolean(entry, "StartupNotify", True)
    action = "Desktop Action ForceQuit"
    config.set_string(action, "Name", "Force Quit (Felix Compat)")
    config.set_locale_string(action, "Name", "zh_CN", "强制退出（Felix 兼容版）")
    config.set_string(action, "Exec", exec_line(*command, "stop", "--root", root))

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                     prefix=".felix-live-", delete=False) as temp:
        draft = Path(temp.name)
        try:
            temp.write(config.to_data()[0])
            temp.flush()
            os.link(draft, target)
        finally:
            draft.unlink()
    return target
