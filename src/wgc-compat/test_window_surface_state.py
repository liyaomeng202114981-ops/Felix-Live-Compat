#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Run with xvfb-run on a disposable X server."""

import os
import struct
import unittest
from unittest.mock import patch

from Xlib import X, Xatom, display, error

from window_surface_state import SurfaceState


class SurfaceReadRaceTest(unittest.TestCase):
    def setUp(self):
        self.connection = display.Display()
        self.addCleanup(self.connection.close)
        root = self.connection.screen().root
        argb = next(depth for depth in self.connection.screen().allowed_depths if depth.depth == 32)
        visual = argb.visuals[0].visual_id
        colormap = root.create_colormap(visual, X.AllocNone)
        self.parent = root.create_window(
            0, 0, 900, 650, 0, 32, X.InputOutput, visual,
            colormap=colormap, border_pixel=0, background_pixel=0xff222222,
        )
        self.parent.set_wm_class("FelixSurfaceRace", "FelixSurfaceRace")
        self.parent.change_property(self.connection.intern_atom("_NET_WM_PID"),
                                    Xatom.CARDINAL, 32, [os.getpid()])
        root.change_property(self.connection.intern_atom("_NET_CLIENT_LIST"),
                             Xatom.WINDOW, 32, [self.parent.id])
        self.parent.map()
        self.stale_input()
        self.state = SurfaceState(self.connection, os.getpid(), self.parent.id)
        self.addCleanup(self.state.close)

    def stale_input(self):
        self.parent.shape_rectangles(0, 2, 0, 0, 0, [(0, 0, 600, 400)])
        self.connection.sync()

    def input_extent(self):
        rectangles = self.parent.shape_get_rectangles(2).rectangles
        return (max(r.x + r.width for r in rectangles),
                max(r.y + r.height for r in rectangles))

    def test_resize_checks_reuse_connection_atom_ids(self):
        with patch.object(self.connection, "intern_atom", side_effect=AssertionError("atom round trip")):
            self.state.check()
            self.state.check()
        self.connection.sync()
        self.assertEqual(self.input_extent(), (900, 650))

    def test_known_window_resize_does_not_enumerate_all_clients(self):
        self.state.check()
        self.stale_input()
        with patch.object(self.state.root, "get_full_property",
                          side_effect=AssertionError("client discovery during known resize")):
            self.state.check(refresh_clients=False)
        self.connection.sync()
        self.assertEqual(self.input_extent(), (900, 650))

    def test_hidden_owner_is_not_sampled(self):
        self.parent.unmap()
        self.connection.sync()
        with patch.object(self.state, "update_owner", side_effect=AssertionError("hidden read")):
            self.state.check()
        self.parent.map()
        self.connection.sync()
        self.state.check()
        self.connection.sync()
        self.assertEqual(self.input_extent(), (900, 650))

    def test_read_race_retries_after_recovery(self):
        for failure, code in ((error.BadMatch, X.BadMatch), (error.BadWindow, X.BadWindow)):
            with self.subTest(failure=failure.__name__):
                self.stale_input()
                packet = struct.pack("=BBHIHB21x", 0, code, 0, self.parent.id, 0, 73)
                raced = failure(self.connection.display, packet)
                with patch.object(self.state.parent, "get_image", side_effect=raced):
                    self.state.check()
                self.assertEqual(self.input_extent(), (600, 400))
                self.state.check()
                self.connection.sync()
                self.assertEqual(self.input_extent(), (900, 650))


if __name__ == "__main__":
    unittest.main()
