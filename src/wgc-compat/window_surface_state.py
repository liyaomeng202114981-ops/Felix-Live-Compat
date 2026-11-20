#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Keep the companion's opaque owner and invisible decoration interactive."""

import argparse
import os
import select
import signal

from Xlib import X, Xatom, display, error, protocol


class SurfaceState:
    def __init__(self, connection, pid, parent_xid):
        self.connection = connection
        self.root = connection.screen().root
        self.pid = pid
        self.parent = connection.create_resource_object("window", parent_xid)
        self.atom = connection.intern_atom
        self.window_class = self.parent.get_wm_class()
        if self.owner(self.parent) != pid or not self.window_class:
            raise ValueError("The companion owner could not be verified")
        self.hidden = {}

    def owner(self, window):
        prop = window.get_full_property(self.atom("_NET_WM_PID"), Xatom.CARDINAL)
        return int(prop.value[0]) if prop is not None and len(prop.value) == 1 else None

    def belongs(self, window):
        return self.owner(window) == self.pid and window.get_wm_class() == self.window_class

    def restore_helper(self, xid):
        previous = self.hidden.pop(xid)
        window = self.connection.create_resource_object("window", xid)
        if not self.belongs(window):
            return
        current = window.get_full_property(self.atom("_NET_WM_WINDOW_OPACITY"), Xatom.CARDINAL)
        if current is not None and list(current.value) == [0]:
            if previous is None:
                window.delete_property(self.atom("_NET_WM_WINDOW_OPACITY"))
            else:
                window.change_property(self.atom("_NET_WM_WINDOW_OPACITY"),
                                       Xatom.CARDINAL, 32, previous)
        window.shape_mask(0, 2, 0, 0, X.NONE)

    def update_owner(self):
        geometry = self.parent.get_geometry()
        rectangles = self.parent.shape_get_rectangles(2).rectangles
        extent = (max((r.x + r.width for r in rectangles), default=0),
                  max((r.y + r.height for r in rectangles), default=0))
        if extent == (geometry.width, geometry.height) or geometry.depth != 32:
            return
        if geometry.width < 700 or geometry.height < 400:
            return
        points = [(10, 10), (geometry.width // 2, 10), (geometry.width - 10, 10),
                  (10, geometry.height // 2), (geometry.width - 10, geometry.height // 2),
                  (10, geometry.height - 10), (geometry.width // 2, geometry.height - 10),
                  (geometry.width - 10, geometry.height - 10)]
        # Reset a stale size only for the verified, opaque companion owner.
        for x, y in points:
            pixel = self.parent.get_image(x, y, 1, 1, X.ZPixmap, 0xffffffff)
            if pixel is None or len(pixel.data) < 4 or pixel.data[3] < 245:
                return
        self.parent.shape_mask(0, 2, 0, 0, X.NONE)
        print(f"Restored companion input {geometry.width}x{geometry.height}", flush=True)

    def invisible_helper(self, window):
        if not self.belongs(window):
            return False
        owner = window.get_wm_transient_for()
        if owner is None or owner.id != self.parent.id:
            return False
        geometry = window.get_geometry()
        if geometry.depth != 32 or geometry.width < 700 or geometry.height < 400:
            return False
        rectangles = window.shape_get_rectangles(0).rectangles
        return not any(r.x < geometry.width and r.y < geometry.height
                       and r.x + r.width > 0 and r.y + r.height > 0 for r in rectangles)

    def check(self):
        if not self.belongs(self.parent):
            raise ValueError("Companion window identity changed")
        self.update_owner()
        active = set()
        for window in self.root.query_tree().children:
            try:
                if not self.invisible_helper(window):
                    continue
                active.add(window.id)
                opacity = window.get_full_property(self.atom("_NET_WM_WINDOW_OPACITY"), Xatom.CARDINAL)
                if window.id not in self.hidden:
                    self.hidden[window.id] = list(opacity.value) if opacity is not None else None
                if opacity is None or list(opacity.value) != [0]:
                    window.change_property(self.atom("_NET_WM_WINDOW_OPACITY"), Xatom.CARDINAL, 32, [0])
                if window.shape_get_rectangles(2).rectangles:
                    window.shape_rectangles(0, 2, 0, 0, 0, [])
                state = window.get_full_property(self.atom("_NET_WM_STATE"), Xatom.ATOM)
                fullscreen = self.atom("_NET_WM_STATE_FULLSCREEN")
                if state is not None and fullscreen in state.value:
                    self.root.send_event(protocol.event.ClientMessage(
                        window=window, client_type=self.atom("_NET_WM_STATE"),
                        data=(32, [0, fullscreen, 0, 2, 0])),
                        event_mask=X.SubstructureNotifyMask | X.SubstructureRedirectMask)
            except error.XError:
                continue
        for xid in set(self.hidden) - active:
            try:
                self.restore_helper(xid)
            except error.XError:
                pass
        self.connection.flush()

    def close(self):
        for xid in tuple(self.hidden):
            try:
                self.restore_helper(xid)
            except error.XError:
                pass
        self.connection.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_pid", type=int)
    parser.add_argument("parent_xid", type=lambda value: int(value, 0))
    args = parser.parse_args()
    stopped = False

    def stop(*_args):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    owner = os.pidfd_open(args.owner_pid)
    connection = display.Display()
    state = SurfaceState(connection, args.owner_pid, args.parent_xid)
    try:
        while not stopped and not select.select([owner], [], [], .1)[0]:
            state.check()
    finally:
        state.close()
        connection.close()
        os.close(owner)


if __name__ == "__main__":
    main()
