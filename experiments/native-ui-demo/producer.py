#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Own synthetic RGBA frames, 320x180 at a requested 30 Hz; no capture or audio."""
import struct
import sys
import time

try:
    frame = 0
    deadline = time.monotonic()
    while True:
        frame += 1
        color = (42, 124, 101, 255) if (frame // 30) % 2 else (137, 67, 100, 255)
        row = bytearray(bytes(color) * 320)
        x = (frame * 3) % 300
        row[x * 4:(x + 20) * 4] = bytes((123, 205, 255, 255)) * 20
        sys.stdout.buffer.write(struct.pack('<4sIQ', b'FLX1', frame, time.monotonic_ns()))
        sys.stdout.buffer.write(row * 180)
        sys.stdout.buffer.flush()
        deadline += 1 / 30
        time.sleep(max(0, deadline - time.monotonic()))
        if time.monotonic() - deadline > .2:
            deadline = time.monotonic()
except (BrokenPipeError, KeyboardInterrupt):
    pass
