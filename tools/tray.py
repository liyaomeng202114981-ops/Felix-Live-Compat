# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Export the running compatibility session's menu to the desktop tray."""

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

MENU_INTERFACE = Gio.DBusNodeInfo.new_for_xml(f"""
<node><interface name="{MENU}">
  <property name="Version" type="u" access="read"/>
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
    def __init__(self, unit):
        self.unit = unit
        self.stop_requested = False
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
                children.append(GLib.Variant("(ia{sv}av)",
                                            (FORCE_QUIT, self.item_properties(FORCE_QUIT, names), [])))
            result = GLib.Variant("(u(ia{sv}av))", (1, (parent, self.item_properties(parent, names), children)))
        elif method == "GetGroupProperties":
            items, names = args
            result = GLib.Variant("(a(ia{sv}))", ([(item, self.item_properties(item, names))
                                                  for item in (items or self.menu_items)
                                                  if item in self.menu_items],))
        elif method == "AboutToShow":
            result = GLib.Variant("(b)", (False,))
        else:  # Event
            result = None
            if args[:2] == (FORCE_QUIT, "clicked") and not self.stop_requested:
                self.stop_requested = True
                GLib.idle_add(self.force_quit)
        invocation.return_value(result)

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
        watch = Gio.bus_watch_name_on_connection(self.bus, WATCHER, Gio.BusNameWatcherFlags.NONE,
                                                self.watcher_appeared, None)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.loop.quit)
        try:
            self.loop.run()
        finally:
            Gio.bus_unwatch_name(watch)
            self.bus.unregister_object(menu)
            self.bus.unregister_object(item)


if __name__ == "__main__":
    unit = sys.argv[1]
    cgroups = Path("/proc/self/cgroup").read_text().splitlines()
    if not re.fullmatch(r"felix-live-compat-[0-9a-f]{16}\.service", unit) or not any(
            entry.startswith("0::") and entry.endswith(f"/{unit}") for entry in cgroups):
        raise SystemExit("Start the tray within its own Felix Live Compat service.")
    Tray(unit).run()
