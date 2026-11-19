#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Draw a visibly changing, self-owned Wayland capture target."""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk


def main():
    window = Gtk.Window(title="Felix Live Compat Test")
    window.set_default_size(800, 450)
    canvas = Gtk.DrawingArea()
    window.set_child(canvas)
    loop = GLib.MainLoop()
    frame = 0

    def draw(_area, context, width, height):
        context.set_source_rgb(*((.8, .08, .14) if frame % 2 else (.07, .62, .26)))
        context.paint()
        context.set_source_rgb(.1, .32, .95)
        context.rectangle(0, 0, width / 8, height / 8)
        context.fill()
        context.set_source_rgb(1, 1, 1)
        context.set_font_size(32)
        context.move_to(40, height / 2)
        context.show_text(f"Felix Live Compat  |  Frame {frame}")

    def tick():
        nonlocal frame
        frame += 1
        canvas.queue_draw()
        return GLib.SOURCE_CONTINUE

    def close(_window):
        loop.quit()
        return False

    canvas.set_draw_func(draw)
    window.connect("close-request", close)
    source = GLib.timeout_add(240, tick)
    window.present()
    try:
        loop.run()
    finally:
        GLib.source_remove(source)


if __name__ == "__main__":
    main()
