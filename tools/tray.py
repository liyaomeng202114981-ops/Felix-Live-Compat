# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Export the running compatibility session's menu to the desktop tray."""

from contextlib import closing
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

from gi.repository import Gio, GLib


ITEM = "org.kde.StatusNotifierItem"
WATCHER = "org.kde.StatusNotifierWatcher"
MENU = "com.canonical.dbusmenu"
ITEM_PATH = "/StatusNotifierItem"
WATCHER_PATH = "/StatusNotifierWatcher"
MENU_PATH = "/Menu"
FORCE_QUIT = 1
OPEN_APP = 2
APP_ACTIONS = {OPEN_APP: "打开直播伴侣", 3: "重置直播伴侣窗口", 4: "退出直播伴侣"}
ORIGINAL_MENU = 5
SEPARATOR = 6

MENU_INTERFACE = Gio.DBusNodeInfo.new_for_xml(f"""
<node><interface name="{MENU}">
  <property name="Version" type="u" access="read"/>
  <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
  <method name="GetLayout">
    <arg name="parent" type="i" direction="in"/>
    <arg name="depth" type="i" direction="in"/>
    <arg name="properties" type="as" direction="in"/>
    <arg name="revision" type="u" direction="out"/>
    <arg name="layout" type="(ia{{sv}}av)" direction="out"/>
  </method>
  <method name="GetGroupProperties">
    <arg name="ids" type="ai" direction="in"/>
    <arg name="properties" type="as" direction="in"/>
    <arg name="items" type="a(ia{{sv}})" direction="out"/>
  </method>
  <method name="AboutToShow">
    <arg name="id" type="i" direction="in"/>
    <arg name="needs_update" type="b" direction="out"/>
  </method>
  <method name="Event">
    <arg name="id" type="i" direction="in"/>
    <arg name="event" type="s" direction="in"/>
    <arg name="data" type="v" direction="in"/>
    <arg name="timestamp" type="u" direction="in"/>
  </method>
</interface></node>
""")


class Tray:
    def __init__(self, unit, cgroup, runtime):
        self.unit = unit
        self.cgroup = cgroup
        self.runtime = runtime
        self.stop_requested = False
        self.native_item = None
        self.revision = 1
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.loop = GLib.MainLoop()
        title = "直播伴侣（Felix 兼容版）"
        self.properties = {
            "Id": ("s", unit.removesuffix(".service")),
            "Title": ("s", title),
            "Category": ("s", "ApplicationStatus"),
            "Status": ("s", "Active"),
            "IconName": ("s", "camera-video-symbolic"),
            "IconAccessibleDesc": ("s", title),
            "ItemIsMenu": ("b", True),
            "Menu": ("o", MENU_PATH),
        }
        properties_xml = "".join(
            f'<property name="{name}" type="{kind}" access="read"/>'
            for name, (kind, _value) in self.properties.items()
        )
        self.item_interface = Gio.DBusNodeInfo.new_for_xml(
            f'<node><interface name="{ITEM}">{properties_xml}</interface></node>')
        self.menu_items = {
            0: {"children-display": GLib.Variant("s", "submenu")},
            FORCE_QUIT: {"label": GLib.Variant("s", "强制退出（Felix 兼容版）")},
        }
        self.application_items = {
            **{key: {"label": GLib.Variant("s", label)} for key, label in APP_ACTIONS.items()},
            ORIGINAL_MENU: {"label": GLib.Variant("s", "直播伴侣原菜单…")},
            SEPARATOR: {"type": GLib.Variant("s", "separator")},
        }

    def get_property(self, _bus, _sender, _path, interface, name):
        if interface == MENU:
            return GLib.Variant("u", 3)  # DBusMenu protocol version
        return GLib.Variant(*self.properties[name])

    def item_properties(self, item, names):
        return {name: value for name, value in self.menu_items[item].items()
                if not names or name in names}

    def menu_call(self, _bus, _sender, _path, _interface, method, parameters, invocation):
        args = parameters.unpack()
        if method == "GetLayout":
            parent, depth, names = args
            if parent not in self.menu_items:
                invocation.return_dbus_error(f"{MENU}.Error.UnknownItem", "Unknown menu item")
                return
            children = []
            if parent == 0 and depth != 0:
                order = (*self.application_items, FORCE_QUIT) if self.native_item else (FORCE_QUIT,)
                children = [GLib.Variant("(ia{sv}av)", (item, self.item_properties(item, names), []))
                            for item in order]
            result = GLib.Variant("(u(ia{sv}av))",
                                  (self.revision, (parent, self.item_properties(parent, names), children)))
        elif method == "GetGroupProperties":
            items, names = args
            result = GLib.Variant("(a(ia{sv}))", ([(item, self.item_properties(item, names))
                                                  for item in (items or self.menu_items)
                                                  if item in self.menu_items],))
        elif method == "AboutToShow":
            result = GLib.Variant("(b)", (False,))
        else:  # Event
            result = None
            item, event = args[:2]
            if item == FORCE_QUIT and event == "clicked" and not self.stop_requested:
                self.stop_requested = True
                GLib.idle_add(self.force_quit)
            elif event == "clicked" and self.native_item and (item in APP_ACTIONS or item == ORIGINAL_MENU):
                GLib.timeout_add(90, self.open_native_menu, item)
        invocation.return_value(result)

    def call(self, owner, path, interface, method, signature, args):
        return self.bus.call_sync(owner, path, interface, method, GLib.Variant(signature, args),
                                  None, Gio.DBusCallFlags.NO_AUTO_START, 800, None).unpack()

    def property_value(self, owner, path, interface, name):
        return self.call(owner, path, "org.freedesktop.DBus.Properties", "Get", "(ss)", (interface, name))[0]

    def own_original_item(self, name):
        if not re.fullmatch(r"org\.kde\.StatusNotifierItem-\d+-\d+", name):
            return None
        daemon = "org.freedesktop.DBus"
        daemon_path = "/org/freedesktop/DBus"
        try:
            owner, = self.call(daemon, daemon_path, daemon, "GetNameOwner", "(s)", (name,))
            pid, = self.call(daemon, daemon_path, daemon, "GetConnectionUnixProcessID", "(s)", (owner,))
            groups = Path(f"/proc/{pid}/cgroup").read_text().splitlines()
            if self.cgroup in groups and self.property_value(owner, ITEM_PATH, ITEM, "Id") == "直播伴侣.exe":
                return owner
        except (OSError, GLib.Error):
            pass
        return None

    def set_native_item(self, owner):
        if self.native_item == owner:
            return
        self.native_item = owner
        if owner:
            self.menu_items.update(self.application_items)
        else:
            for key in self.application_items:
                self.menu_items.pop(key, None)
        self.revision += 1
        self.bus.emit_signal(None, MENU_PATH, MENU, "LayoutUpdated", GLib.Variant("(ui)", (self.revision, 0)))

    def refresh_native_item(self, *_args):
        try:
            names = self.property_value(WATCHER, WATCHER_PATH, WATCHER, "RegisteredStatusNotifierItems")
        except GLib.Error:
            return
        self.set_native_item(next((owner for name in names if (owner := self.own_original_item(name))), None))

    @staticmethod
    def expire_action(path, inode):
        try:
            if path.stat().st_ino == inode:
                path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        return GLib.SOURCE_REMOVE

    def open_native_menu(self, action):
        from Xlib import display, error

        owner = self.native_item
        if not owner:
            return GLib.SOURCE_REMOVE
        request = self.runtime / "tray-action"
        inode = None
        try:
            with closing(display.Display()) as connection:
                position = connection.screen().root.query_pointer()
            if action in APP_ACTIONS and action != OPEN_APP:
                stage = self.runtime / "tray-action.next"
                stage.write_text(f"{action - OPEN_APP}\n", encoding="ascii")
                inode = stage.stat().st_ino
                os.replace(stage, request)
                GLib.timeout_add(1500, self.expire_action, request, inode)
            method = "Activate" if action == OPEN_APP else "ContextMenu"
            self.call(owner, ITEM_PATH, ITEM, method, "(ii)", (position.root_x, position.root_y))
        except (OSError, GLib.Error, error.DisplayError, error.XError) as exc:
            if inode is not None:
                self.expire_action(request, inode)
            print(f"Tray could not forward the companion action: {exc}", file=sys.stderr, flush=True)
        return GLib.SOURCE_REMOVE

    def force_quit(self):
        try:
            # Queue the bounded systemd stop without waiting inside the unit being stopped.
            subprocess.run(["systemctl", "--user", "--no-block", "stop", self.unit],
                           check=True, timeout=3)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"Tray could not stop {self.unit}: {exc}", file=sys.stderr, flush=True)
            self.stop_requested = False
        return GLib.SOURCE_REMOVE

    def watcher_appeared(self, connection, _name, owner):
        connection.call(owner, WATCHER_PATH, WATCHER, "RegisterStatusNotifierItem",
                        GLib.Variant("(s)", (ITEM_PATH,)), None, Gio.DBusCallFlags.NO_AUTO_START,
                        3000, None, self.registration_finished)
        self.refresh_native_item()

    def watcher_vanished(self, *_args):
        self.set_native_item(None)

    def registration_finished(self, connection, result):
        try:
            connection.call_finish(result)
            print(f"Tray registered for {self.unit}", flush=True)
        except GLib.Error as exc:
            print(f"Tray registration failed: {exc}", file=sys.stderr, flush=True)

    def run(self):
        item = self.bus.register_object(ITEM_PATH, self.item_interface.interfaces[0],
                                        None, self.get_property, None)
        menu = self.bus.register_object(MENU_PATH, MENU_INTERFACE.interfaces[0],
                                        self.menu_call, self.get_property, None)
        watch_signals = [self.bus.signal_subscribe(WATCHER, WATCHER, signal_name, WATCHER_PATH,
                                                   None, Gio.DBusSignalFlags.NONE, self.refresh_native_item)
                         for signal_name in ("StatusNotifierItemRegistered", "StatusNotifierItemUnregistered")]
        watch = Gio.bus_watch_name_on_connection(self.bus, WATCHER, Gio.BusNameWatcherFlags.NONE,
                                                self.watcher_appeared, self.watcher_vanished)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.loop.quit)
        try:
            self.loop.run()
        finally:
            Gio.bus_unwatch_name(watch)
            for subscription in watch_signals:
                self.bus.signal_unsubscribe(subscription)
            self.bus.unregister_object(menu)
            self.bus.unregister_object(item)


if __name__ == "__main__":
    unit = sys.argv[1]
    cgroup = next((entry for entry in Path("/proc/self/cgroup").read_text().splitlines()
                   if entry.startswith("0::")), "")
    if not re.fullmatch(r"felix-live-compat-[0-9a-f]{16}\.service", unit) or not cgroup.endswith(f"/{unit}"):
        raise SystemExit("Start the tray within its own Felix Live Compat service.")
    Tray(unit, cgroup, Path(os.environ["RUNTIME_DIRECTORY"])).run()
