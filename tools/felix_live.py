#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Install and run the official Windows client in a new Felix compatibility prefix."""

import argparse
from contextlib import suppress
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import time

from assets import obtain
from desktop import application_id, desktop_path, instance_key, register_desktop
from preflight import check_dependencies
from wine_runtime import install_wine_modules


KIT = Path(__file__).resolve().parents[1]
SOURCE = KIT / "src/wgc-compat"
sys.path.insert(0, str(SOURCE))
from install_trial import stage_capture

RUNNER_NAME = "felix-proton-uu-test-0.1.0-test.1"
MARKER = ".felix-live-compat"
WINDOW_CLASS = "直播伴侣.exe".encode()
LAUNCHER = "直播伴侣 Launcher.exe"
DISPLAY_ENV = ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
               "XDG_SESSION_TYPE", "DBUS_SESSION_BUS_ADDRESS", "XDG_CURRENT_DESKTOP",
               "PIPEWIRE_RUNTIME_DIR", "PIPEWIRE_REMOTE", "DESKTOP_STARTUP_ID")
PREFIX_ENV = {"WINEDEBUG": "-all", "PROTON_LOG": "0", "PROTON_NVIDIA_NVENC": "1",
              "PROTON_FORCE_NVAPI": "1"}


def wine_command(root, *args):
    return [root / "shorin-proton-wrapper", "--prefix", root / "prefix",
            "--runner", root / "runner/proton", *args]


def find_launcher(root):
    drive = root / "prefix/pfx/drive_c"
    for directory in ("Program Files (x86)", "Program Files"):
        app = drive / directory / "webcast_mate" / LAUNCHER
        if app.is_file():
            return app
    raise FileNotFoundError("Official launcher missing from the default installation path")


def install(root, installer, assets, interactive):
    if not installer.is_file() or installer.suffix.lower() != ".exe":
        raise ValueError("Supply the official Windows .exe installer")
    if installer.is_relative_to(root):
        raise ValueError("Keep the official installer outside the new installation directory")
    check_dependencies()
    if os.path.lexists(desktop_path(root)):
        raise FileExistsError(f"Desktop entry already exists: {desktop_path(root)}")
    built = KIT / "payload"
    subprocess.run(["sha256sum", "--strict", "--check", "SHA256SUMS"], cwd=built, check=True)
    root.mkdir(mode=0o700, parents=True)
    with obtain("runner", assets) as archive:
        subprocess.run(["tar", "--zstd", "-xf", archive, "--no-same-owner", "-C", root], check=True)
    (root / RUNNER_NAME).rename(root / "runner")
    install_wine_modules(built, root / "runner")
    with obtain("wrapper", assets) as wrapper:
        target = root / "shorin-proton-wrapper"
        shutil.copyfile(wrapper, target)
        target.chmod(0o700)
    payload = root / "payload"
    shutil.copytree(built, payload)
    shutil.copy2(payload / "window-stream", payload / "window-stream-interactive")
    env = os.environ | PREFIX_ENV | {"WINEDLLOVERRIDES": "winemenubuilder.exe=d"}
    subprocess.run(wine_command(root, "--init"), env=env, check=True)
    arguments = () if interactive else ("/S",)
    subprocess.run(wine_command(root, installer, *arguments), env=env, check=True)
    launcher = find_launcher(root)
    stage_capture(payload, root / "prefix", root / "runner", root / "shorin-proton-wrapper",
                  wine_env=env)
    for name in ("tools", "src"):
        shutil.copytree(KIT / name, root / "launcher" / name,
                        ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(KIT / "assets.json", root / "launcher/assets.json")
    (root / MARKER).write_text("1\n", encoding="ascii")
    print(f"Ready: {root}")
    print(f"Desktop entry: {register_desktop(root, launcher)}")


def service_name(root):
    return f"felix-live-compat-{instance_key(root)}"


def launch(root, direct):
    unit = service_name(root)
    if subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit]).returncode == 0:
        print(f"Already running: {unit}")
        return
    env = [f"--setenv={name}={os.environ[name]}" for name in DISPLAY_ENV if name in os.environ]
    flags = ["--direct"] if direct else []
    subprocess.run(["systemd-run", "--user", "--collect", "--service-type=exec", f"--unit={unit}",
                    f"--property=RuntimeDirectory={unit}", "--property=RuntimeDirectoryMode=0700",
                    "--property=KillMode=control-group", "--property=TimeoutStopSec=5s",
                    *env, "--", sys.executable, "-B", str(Path(__file__).resolve()),
                    "run-session", "--root", root, *flags], check=True)


def main_window(connection, pids):
    from Xlib import X, error

    atom = connection.intern_atom
    windows = connection.screen().root.get_full_property(atom("_NET_CLIENT_LIST_STACKING"),
                                                         X.AnyPropertyType)
    if windows is None:
        return None
    for xid in reversed(windows.value):
        window = connection.create_resource_object("window", int(xid))
        try:
            own = window.get_full_property(atom("_NET_WM_PID"), X.AnyPropertyType)
            if not own or str(own.value[0]) not in pids:
                continue
            raw = window.get_full_property(atom("WM_CLASS"), X.AnyPropertyType)
            if raw is None or WINDOW_CLASS not in raw.value.split(b"\0"):
                continue
            if window.get_wm_transient_for() is not None:
                continue
            title = window.get_full_property(atom("_NET_WM_NAME"), X.AnyPropertyType)
            if title is not None and "登录".encode() in title.value:
                continue
            state = window.get_full_property(atom("_NET_WM_STATE"), X.AnyPropertyType)
            if state is not None and atom("_NET_WM_STATE_SKIP_TASKBAR") in state.value:
                continue
            if window.get_attributes().map_state == X.IsViewable:
                return int(xid), int(own.value[0])
        except error.BadWindow:
            continue
    return None


def start_helpers(root, runtime, payload, xid, pid):
    source_store = (root / "prefix/pfx/drive_c/users/steamuser/AppData/Roaming/"
                    "webcast_mate/WBStore/sourceStore.json")
    broker = [sys.executable, "-B", SOURCE / "inapp.py", runtime, payload,
              str(pid), "--source-store", source_store, "--parent-xid", hex(xid)]
    actions = wine_command(root, payload / "inapp_actions.exe",
                           "Z:" + str(runtime).replace("/", "\\"))
    presenter = [sys.executable, "-B", SOURCE / "popup_first_paint.py", str(pid), hex(xid)]
    children = []
    try:
        children.append(subprocess.Popen(broker, env=os.environ | {"FELIX_WGC_DYNAMIC_TITLE": "1"}))
        actions_env = os.environ | PREFIX_ENV | {
            "PRESSURE_VESSEL_FILESYSTEMS_RW": str(runtime),
        }
        children.append(subprocess.Popen(actions, env=actions_env))
        children.append(subprocess.Popen(presenter))
        children.append(subprocess.Popen([
            sys.executable, "-B", SOURCE / "window_surface_state.py", str(pid), hex(xid),
        ]))
    except OSError:
        stop_helpers(children)
        raise
    return children


def stop_helpers(children):
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def run_session(root, direct):
    from Xlib import display
    from douyin_native import app_environment

    unit = service_name(root)
    runtime = Path(os.environ["RUNTIME_DIRECTORY"])
    if runtime != Path(os.environ["XDG_RUNTIME_DIR"]) / unit:
        raise ValueError("Start the session through the launch command")
    groups = Path("/proc/self/cgroup").read_text().splitlines()
    unified = next((item[3:] for item in groups if item.startswith("0::")), None)
    if unified is None:
        raise RuntimeError("A cgroup v2 user session is required")
    membership = Path("/sys/fs/cgroup") / unified.lstrip("/") / "cgroup.procs"
    payload = root / "payload"
    env = os.environ | PREFIX_ENV | app_environment("in-app", payload, runtime)
    env.update(WINEDLLOVERRIDES="d3d11=n;graphicscapture=n;winemenubuilder.exe=d",
               WINE_LAYERED_OVERLAY_ALPHA="1", WINE_X11_NATIVE_MAXIMIZED_MOVE="1",
               WINE_X11_NO_FULLSCREEN_LAYERED_HELPER="1",
               WINE_X11_NO_FULLSCREEN_HELPER_CLASS="Chrome_WidgetWin_1",
               WINE_X11_INVISIBLE_DECORATION="1",
               WINE_X11_WM_INSTANCE=application_id(root),
               WINE_X11_WM_INSTANCE_EXE=WINDOW_CLASS.decode())
    arguments = ["--force-renderer-accessibility=complete"]
    if direct:
        for name in ("http_proxy", "https_proxy", "all_proxy", "ftp_proxy", "no_proxy"):
            env.pop(name, None)
            env.pop(name.upper(), None)
        arguments.append("--no-proxy-server")
    launcher = find_launcher(root)
    env.pop("WINE_FELIX_TRAY_OWNER", None)
    connection = display.Display()
    children = []
    tray = None
    owner = None
    candidate = None
    appeared = 0.0
    stopping = False
    deadline = time.monotonic() + 600

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        try:
            tray = subprocess.Popen([sys.executable, "-B", KIT / "tools/tray.py", unit + ".service"])
            ready = runtime / "tray-bus"
            tray_deadline = time.monotonic() + 1
            while not stopping and tray.poll() is None and time.monotonic() < tray_deadline:
                if ready.is_file():
                    name = ready.read_text(encoding="ascii").strip()
                    if re.fullmatch(r":1\.[0-9]+", name):
                        env["WINE_FELIX_TRAY_OWNER"] = name
                    break
                time.sleep(.025)
        except OSError as exc:
            print(f"Tray could not start: {exc}", file=sys.stderr, flush=True)
        if stopping:
            return
        subprocess.Popen(wine_command(root, launcher, *arguments), cwd=launcher.parent, env=env)
        while not stopping:
            if owner is None:
                window = main_window(connection, set(membership.read_text().split()))
                now = time.monotonic()
                if window != candidate:
                    candidate = window
                    appeared = now
                if window is not None and now - appeared >= 1.2:
                    xid, pid = window
                    with suppress(ProcessLookupError):
                        owner = os.pidfd_open(pid)
                    if owner is not None:
                        children = start_helpers(root, runtime, payload, xid, pid)
                        print(f"Companion ready: {xid:#x}", flush=True)
                elif now >= deadline:
                    raise RuntimeError("Timed out waiting for the official client window")
                else:
                    time.sleep(.2)
            elif select.select([owner], [], [], .5)[0]:
                return
            elif any(child.poll() is not None for child in children):
                raise RuntimeError("A compatibility helper stopped while the client was running")
    finally:
        stop_helpers(([tray] if tray is not None else []) + children)
        if owner is not None:
            os.close(owner)
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    for name in ("install", "launch", "stop", "run-session"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=lambda path: Path(path).expanduser().resolve(), required=True)
        if name == "install":
            command.add_argument("--installer", type=lambda path: Path(path).expanduser().resolve(),
                                 required=True)
            command.add_argument("--assets", type=lambda path: Path(path).expanduser().resolve())
            command.add_argument("--interactive", action="store_true")
        elif name in ("launch", "run-session"):
            command.add_argument("--direct", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            check_dependencies()
        elif args.command == "install":
            install(args.root, args.installer, args.assets, args.interactive)
        else:
            (args.root / MARKER).read_text()
            if args.command == "stop":
                subprocess.run(["systemctl", "--user", "stop", service_name(args.root)], check=True)
            elif args.command == "launch":
                launch(args.root, args.direct)
            else:
                run_session(args.root, args.direct)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
