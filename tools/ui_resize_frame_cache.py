#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Own a copy of the client surface for drag-time presentation."""
import ctypes as C
from contextlib import contextmanager
import time
from Xlib import X, error


class _Transform(C.Structure):
    _fields_ = [('matrix', (C.c_int32 * 3) * 3)]  # XFixed: signed 16.16


class _XError(C.Structure):
    _fields_ = [('type', C.c_int), ('display', C.c_void_p),
                ('resourceid', C.c_ulong), ('serial', C.c_ulong),
                ('error_code', C.c_ubyte), ('request_code', C.c_ubyte),
                ('minor_code', C.c_ubyte)]


class FrameCache:
    MAX_PIXELS = 16_777_216
    MAX_BACKGROUNDS = 2

    def __init__(self, xdisplay, root, depth=24):
        self.d, self.root, self.depth = xdisplay, int(root.id if hasattr(root, 'id') else root), depth
        self.c = None
        self.cache = self.sample = 0
        self.backgrounds = set()
        self.last_good_monotonic = 0.0
        self.content_dimensions = (0, 0)
        self.last_sample = self.last_error = None
        screen = xdisplay.screen()
        if depth != 24 or screen.root_depth != depth or screen.root.id != self.root:
            raise ValueError('Only the default screen RGB888 depth-24 visual is supported')
        visual = next(v for dep in screen.allowed_depths for v in dep.visuals
                      if v.visual_id == screen.root_visual)
        if (visual.red_mask, visual.green_mask, visual.blue_mask) != (0xff0000, 0xff00, 0xff):
            raise ValueError('Unsupported visual masks')
        info = xdisplay.display.info
        fmt = next(f for f in info.pixmap_formats if f.depth == depth)
        if fmt.bits_per_pixel not in (24, 32):
            raise ValueError('Unsupported pixel storage')
        self.bytes_per_pixel = fmt.bits_per_pixel // 8
        self.scanline_pad = fmt.scanline_pad
        self.byteorder = 'little' if info.image_byte_order == X.LSBFirst else 'big'
        self.x = C.CDLL('libX11.so.6')
        self.r = C.CDLL('libXrender.so.1')
        P, U, I = C.c_void_p, C.c_ulong, C.c_int
        signatures = {
            'XOpenDisplay': (P, [C.c_char_p]), 'XCloseDisplay': (I, [P]),
            'XDefaultScreen': (I, [P]), 'XDefaultVisual': (P, [P, I]),
            'XCreatePixmap': (U, [P, U, C.c_uint, C.c_uint, C.c_uint]),
            'XFreePixmap': (I, [P, U]), 'XSync': (I, [P, I]),
            'XSetErrorHandler': (P, [P]),
            'XRenderFindVisualFormat': (P, [P, P]),
            'XRenderCreatePicture': (U, [P, U, P, U, P]),
            'XRenderFreePicture': (None, [P, U]),
            'XRenderSetPictureTransform': (None, [P, U, C.POINTER(_Transform)]),
            'XRenderComposite': (None, [P, I, U, U, U] + [I]*6 + [C.c_uint]*2),
        }
        for name, (result, args) in signatures.items():
            fn = getattr(self.r if name.startswith('XRender') else self.x, name)
            fn.restype, fn.argtypes = result, args
        self.c = self.x.XOpenDisplay(xdisplay.get_display_name().encode())
        if not self.c:
            raise RuntimeError('Cannot open separate X11 connection')
        try:
            with self._checked():
                v = self.x.XDefaultVisual(self.c, self.x.XDefaultScreen(self.c))
                self.format = self.r.XRenderFindVisualFormat(self.c, v)
                if not self.format:
                    raise RuntimeError('No XRender format for default visual')
                self.r.XRenderFindStandardFormat.restype = C.c_void_p
                self.r.XRenderFindStandardFormat.argtypes = [C.c_void_p, C.c_int]
                self.format_argb = self.r.XRenderFindStandardFormat(self.c, 0)  # PictStandardARGB32
                if not self.format_argb:
                    raise RuntimeError('No XRender ARGB32 format')
                self.sample = self._pixmap(64, 40)
        except Exception:
            self.close()
            raise

    @contextmanager
    def _checked(self):
        """Trap errors on our C connection; always restore the process-wide handler.

        The embedding program must not concurrently use C Xlib error handlers.
        Python-Xlib's separate implementation is unaffected.
        """
        if not self.c:
            raise RuntimeError('FrameCache is closed')
        errors = []
        callback_type = C.CFUNCTYPE(C.c_int, C.c_void_p, C.POINTER(_XError))
        previous = None

        def handler(display, event):
            if display == self.c:
                e = event.contents
                errors.append((e.error_code, e.request_code, e.minor_code))
                return 0
            return callback_type(previous)(display, event) if previous else 0

        callback = callback_type(handler)
        previous = self.x.XSetErrorHandler(C.cast(callback, C.c_void_p))
        try:
            yield
        finally:
            self.x.XSync(self.c, 0)
            self.x.XSetErrorHandler(previous)
        if errors:
            raise RuntimeError('XRender/X11 errors: ' + repr(errors))

    def _pixmap(self, width, height):
        if not (0 < width <= 16384 and 0 < height <= 16384 and width*height <= self.MAX_PIXELS):
            raise ValueError('Pixmap dimensions exceed bounds')
        return self.x.XCreatePixmap(self.c, self.root, width, height, self.depth)

    def _discard(self, pixmap):
        # Allocation can return an XID before the server rejects the request.
        # Freeing such an XID must not make capture() raise from its cleanup.
        try:
            with self._checked():
                self.x.XFreePixmap(self.c, pixmap)
        except RuntimeError as exc:
            self.last_error = str(exc)

    def _copy(self, source, destination, sw, sh, dw, dh, src_format=None):
        src = dst = 0
        try:
            src = self.r.XRenderCreatePicture(self.c, source, src_format or self.format, 0, None)
            dst = self.r.XRenderCreatePicture(self.c, destination, self.format, 0, None)
            transform = _Transform()
            transform.matrix[0][0] = round(sw / dw * 65536)
            transform.matrix[1][1] = round(sh / dh * 65536)
            transform.matrix[2][2] = 65536
            self.r.XRenderSetPictureTransform(self.c, src, C.byref(transform))
            self.r.XRenderComposite(self.c, 1, src, 0, dst, 0, 0, 0, 0, 0, 0, dw, dh)
        finally:
            if dst:
                self.r.XRenderFreePicture(self.c, dst)
            if src:
                self.r.XRenderFreePicture(self.c, src)

    def capture(self, window):
        """Copy only this window. Reject nearly uniform black/white, retaining cache."""
        source, candidate = None, 0
        self.last_error = None
        try:
            if not self.c:
                raise RuntimeError('FrameCache is closed')
            if window.id == self.root:
                raise ValueError('Root capture is forbidden')
            failures = []
            source = window.composite_name_window_pixmap(onerror=lambda e, r: failures.append(e))
            self.d.sync()  # Source name must exist before the C connection uses it.
            if failures:
                raise RuntimeError('Window pixmap unavailable')
            geometry = source.get_geometry()
            if geometry.depth not in (self.depth, 32):
                raise ValueError('Unsupported source depth %d' % geometry.depth)
            src_format = self.format_argb if geometry.depth == 32 else self.format
            width, height = geometry.width, geometry.height
            with self._checked():
                candidate = self._pixmap(width, height)
                self._copy(source.id, candidate, width, height, width, height, src_format)
                # Sample the owned snapshot, never a mutable window after readback.
                self._copy(candidate, self.sample, width, height, 64, 40)
            sample = self.d.create_resource_object('pixmap', self.sample)
            raw = sample.get_image(0, 0, 64, 40, X.ZPixmap, 0xffffff).data
            stride = ((64*self.bytes_per_pixel*8 + self.scanline_pad-1) // self.scanline_pad) * (self.scanline_pad//8)
            if len(raw) < stride*40:
                raise RuntimeError('Truncated sample image')
            lo, hi, total, black, white = 255, 0, 0, 0, 0
            for y in range(40):
                for x in range(64):
                    offset = y*stride + x*self.bytes_per_pixel
                    pixel = int.from_bytes(raw[offset:offset+self.bytes_per_pixel], self.byteorder)
                    channels = ((pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255)
                    lo, hi, total = min(lo, *channels), max(hi, *channels), total+sum(channels)
                    black += max(channels) <= 20
                    white += min(channels) >= 235
            self.last_sample = {'min': lo, 'max': hi, 'mean': total/(64*40*3),
                                'near_black': black/(64*40), 'near_white': white/(64*40)}
            if (hi <= 20 or lo >= 235 or self.last_sample['mean'] <= 2
                    or self.last_sample['mean'] >= 253 or black >= .95*64*40 or white >= .95*64*40):
                return False
            old = self.cache
            self.cache, candidate = candidate, 0
            self.content_dimensions = (width, height)
            self.last_good_monotonic = time.monotonic()
            if old:
                self._discard(old)
            return True
        except (error.XError, RuntimeError, ValueError) as exc:
            self.last_error = str(exc)
            return False
        finally:
            if candidate and self.c:
                self._discard(candidate)
            if source:
                source.free(onerror=lambda e, r: None)
                self.d.sync()  # Never leave Python-owned resource IDs outstanding.

    def render_background(self, width, height):
        """Return a C-owned pixmap ID; caller must call free_background for it."""
        if not self.cache:
            raise RuntimeError('No valid frame cached')
        if len(self.backgrounds) >= self.MAX_BACKGROUNDS:
            raise RuntimeError('Free an old background before allocating another')
        pixmap = 0
        try:
            with self._checked():
                pixmap = self._pixmap(int(width), int(height))
                self._copy(self.cache, pixmap, *self.content_dimensions, int(width), int(height))
            self.backgrounds.add(pixmap)
            return pixmap
        except Exception:
            if pixmap:
                self._discard(pixmap)
            raise

    def free_background(self, pixmap):
        if pixmap not in self.backgrounds:
            return
        self.d.sync()  # Process any Python requests using this pixmap first.
        with self._checked():
            self.x.XFreePixmap(self.c, pixmap)
        self.backgrounds.remove(pixmap)

    def close(self):
        if not self.c:
            return
        # All resources belong to this connection; XCloseDisplay frees them.
        self.d.sync()
        self.x.XCloseDisplay(self.c)
        self.c = None
        self.cache = self.sample = 0
        self.backgrounds.clear()
        self.content_dimensions = (0, 0)
