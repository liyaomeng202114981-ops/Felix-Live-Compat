#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Paced live resize with a short-lived valid-frame preview overlay."""
import argparse
import os
from pathlib import Path
import select
import sys
import time
import threading
from Xlib import display as xdisplay, protocol
from types import SimpleNamespace
from Xlib import X, Xatom, error
from Xlib.ext import shape


import ui_resize_grips as base
try:
    from ui_resize_frame_cache import FrameCache
except ImportError:
    FrameCache = None
LIVE_FRAMES = os.environ.get('FELIX_LIVE_FRAMES') == '1'


def resize_rect(rect, origin, point, direction):
    """Pure geometry: opposite edges stay fixed at the original rectangle."""
    x, y, w, h = rect
    dx, dy = point[0]-origin[0], point[1]-origin[1]
    if direction in (0, 6, 7):
        new_w = max(200, w-dx)
        x, w = x+w-new_w, new_w
    if direction in (2, 3, 4):
        w = max(200, w+dx)
    if direction in (0, 1, 2):
        new_h = max(200, h-dy)
        y, h = y+h-new_h, new_h
    if direction in (4, 5, 6):
        h = max(200, h+dy)
    return x, y, w, h


class LiveGrips(base.Grips):
    INTERVAL = 1/60
    FRAME_TIMEOUT = .500
    INTERVAL_REQUEST = .10
    FINAL_TIMEOUT = .900

    def __init__(self, args):
        self.drag = self.cache = self.preview = None
        self.background = 0
        self.pointer_owned = self.escape_registered = False
        self.next_tick = 0.0
        super().__init__(args)
        self.escape_key = self.d.keysym_to_keycode(0xff1b)

    def _geometry(self):
        g = self.parent.get_geometry()
        p = self.root.translate_coords(self.parent, 0, 0)
        return p.x, p.y, g.width, g.height

    def _foreground(self):
        active = self.prop(self.root, '_NET_ACTIVE_WINDOW', Xatom.WINDOW)
        return bool(self.parent and active is not None and len(active)
                    and int(active[0]) == self.parent.id
                    and self.parent.get_attributes().map_state == X.IsViewable)

    def _ancestor(self):
        window = self.parent
        for _ in range(16):
            tree = window.query_tree()
            if tree.parent.id == self.root.id:
                return window
            window = tree.parent
        raise RuntimeError('Cannot identify root sibling for preview')

    def _overlapping_window_above(self, rect):
        """Do not cover an already-visible popup or unrelated window."""
        ancestor = self._ancestor()
        siblings = self.root.query_tree().children
        index = next(i for i, w in enumerate(siblings) if w.id == ancestor.id)
        x, y, width, height = rect
        for window in siblings[index+1:]:
            try:
                attrs = window.get_attributes()
                if attrs.map_state != X.IsViewable or attrs.win_class != X.InputOutput:
                    continue
                g = window.get_geometry()
                if g.width > 1 and g.height > 1 and x < g.x+g.width and g.x < x+width and y < g.y+g.height and g.y < y+height:
                    return True
            except error.XError:
                continue
        return False

    def _request(self, rect):
        self.message('_NET_MOVERESIZE_WINDOW', [0x1F0A] + [n & 0xffffffff for n in rect])
        self.d.flush()
        self.drag['sent'], self.drag['sent_at'], self.drag['waiting'] = rect, time.monotonic(), True
        self.log('resize_request',rectangle=rect)

    def _show(self, rect):
        if not self.drag['preview']:
            return
        last = self.drag.get('shown')
        if not last or abs(rect[2]-last[2]) >= 16 or abs(rect[3]-last[3]) >= 16 or rect[:2] != last[:2]:
            self.drag['shown'] = rect
            try:
                ch = [w.id for w in self.root.query_tree().children]
                self.log('show', rectangle=list(rect), preview=hex(self.preview.id) if self.preview else None,
                         mapped=None if not self.preview else self.preview.get_attributes().map_state,
                         stack=(ch.index(self.preview.id), ch.index(self.parent.id)) if self.preview and self.preview.id in ch else None)
            except Exception:
                pass
        pixmap = self.cache.render_background(rect[2], rect[3])
        old = self.background
        self.background = pixmap
        if self.preview is None:
            screen = self.d.screen()
            self.preview = self.root.create_window(*rect, 0, screen.root_depth,
                X.InputOutput, screen.root_visual, override_redirect=True,
                background_pixmap=pixmap, event_mask=0)
            self.preview.set_wm_name('WeGame resize preview')
            self.preview.set_wm_class('wegame-resize-preview', 'WeGameResizePreview')
            self.preview.set_wm_hints(flags=1, input=0)
            self.preview.shape_rectangles(shape.SO.Set, shape.SK.Input, X.Unsorted, 0, 0, [])
            if self.preview.shape_get_rectangles(shape.SK.Input).rectangles:
                raise RuntimeError('Preview input shape is not empty')
            self.log('preview_created',window=hex(self.preview.id),main=hex(self.parent.id))
        else:
            self.preview.change_attributes(background_pixmap=pixmap)
            self.preview.configure(x=rect[0], y=rect[1], width=rect[2], height=rect[3])
        # Never raise above unrelated windows: insert directly above the main's
        # actual root ancestor. Root preview is not in the captured subtree.
        self.preview.configure(sibling=self._ancestor(), stack_mode=X.Above)
        self.preview.clear_area()
        self.preview.map()
        if old:
            self.cache.free_background(old)
        else:
            self.d.sync()

    def _cleanup(self, reason, escape_event=None):
        drag, self.drag = self.drag, None
        def safely(fn):
            try:
                fn()
            except Exception as exc:
                self.log('cleanup_error',error=str(exc))
        # Remove the visual first, even if a later cleanup operation fails.
        if self.preview is not None:
            preview, self.preview = self.preview, None
            safely(preview.unmap)
            safely(preview.destroy)
        if self.pointer_owned:
            self.pointer_owned = False
            safely(lambda: self.d.ungrab_pointer(X.CurrentTime))
        if self.escape_registered:
            self.escape_registered = False
            if self.parent:
                safely(lambda: self.parent.ungrab_key(self.escape_key, X.AnyModifier,
                                                      onerror=lambda e, r: None))
        if escape_event is not None:
            # This keyboard grab was activated by our own Escape binding.
            safely(lambda: self.d.ungrab_keyboard(escape_event.time))
        safely(self.d.flush)
        if self.cache is not None:
            cache, self.cache = self.cache, None
            self.background = 0
            safely(cache.close)
        if drag:
            self.last_scan = 0
            self.log('resize_end',reason=reason)

    def _fallback(self, direction, reason):
        self._cleanup(reason)
        try:
            p = self.root.query_pointer()
            if self._foreground() and p.mask & X.Button1Mask:
                super().begin_drag(SimpleNamespace(time=X.CurrentTime,
                    root_x=p.root_x, root_y=p.root_y), direction)
        except error.XError:
            pass

    def begin_drag(self, event, direction):
        if self.drag or self.cache or self.preview:
            self._cleanup('superseded_gesture')
        if direction == 8 or FrameCache is None:
            return super().begin_drag(event, direction)
        try:
            if not self._foreground() or self.qualify(self.parent) != self.identity:
                return super().begin_drag(event, direction)
            point = self.root.query_pointer()
            if not point.mask & X.Button1Mask:
                return
            self.ensure_min_size()
            rect = self._geometry()
            self.cache = FrameCache(self.d, self.root)
            if not self.cache.capture(self.parent):
                raise RuntimeError('No initial valid frame')
            failures = []
            self.parent.grab_key(self.escape_key, X.AnyModifier, False,
                                 X.GrabModeAsync, X.GrabModeAsync,
                                 onerror=lambda e, r: failures.append(e))
            self.escape_registered = True
            self.d.sync()
            if failures:
                raise RuntimeError('Cannot register Escape on the main window')
            status = self.parent.grab_pointer(False,
                X.ButtonPressMask | X.ButtonReleaseMask | X.PointerMotionMask,
                X.GrabModeAsync, X.GrabModeAsync, X.NONE, self.cursors[direction], event.time)
            if status != X.GrabSuccess:
                raise RuntimeError('Cannot acquire resize pointer grab')
            self.pointer_owned = True
            now = time.monotonic()
            self.drag = dict(original=rect, origin=(event.root_x, event.root_y),
                target=rect, sent=rect, sent_at=now, waiting=False,
                direction=direction, started=now, finishing=0.0,
                preview=PREVIEW and not self._overlapping_window_above(rect))
            self.next_tick = now
            self.log('resize_start',direction=direction,rectangle=rect,preview=self.drag['preview'])
        except Exception as exc:
            self.log('resize_failure',error=str(exc))
            self._fallback(direction, 'initialization_failed')

    def _enforce_final(self, rect):
        """松手后应用/客户端可能把尺寸改回去（Wine 重排时序）；250ms 后校验并补发一次。"""
        if not rect:
            return
        try:
            d = xdisplay.Display()
        except Exception:
            return

        def attempt(n):
            try:
                w = d.create_resource_object('window', self.parent.id)
                g = w.get_geometry()
                if abs(g.width - rect[2]) <= 2 and abs(g.height - rect[3]) <= 2:
                    return
                msg = protocol.event.ClientMessage(window=w, client_type=d.intern_atom('_NET_MOVERESIZE_WINDOW'),
                    data=(32, [0x1F0A] + [int(v) & 0xffffffff for v in rect]))
                d.screen().root.send_event(msg, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
                d.flush()
                self.log('enforce_final', rectangle=list(rect), attempt=n, actual=[g.x, g.y, g.width, g.height])
                if n < 3:
                    threading.Timer(.25, attempt, args=(n + 1,)).start()
            except Exception as exc:
                self.log('enforce_failed', error=str(exc))

        threading.Timer(.25, attempt, args=(1,)).start()

    def _finish(self, x, y):
        if not self.drag or self.drag['finishing']:
            return
        self.drag['target'] = resize_rect(self.drag['original'], self.drag['origin'],
                                         (x, y), self.drag['direction'])
        want = (self.drag['target'][2], self.drag['target'][3])
        if want != self.drag.get('want'):
            self.drag['want'] = want
            self._request(self.drag['target'])  # One final target; no more interim requests.
        self.drag['finishing'] = time.monotonic() + self.FINAL_TIMEOUT
        if self.pointer_owned:
            self.d.ungrab_pointer(X.CurrentTime)
            self.pointer_owned = False
            self.d.flush()

    def _tick(self):
        if not self.drag:
            return
        direction = self.drag['direction']
        try:
            now = time.monotonic()
            if not self._foreground():
                return self._cleanup('focus_or_visibility_changed')
            if now-self.drag['started'] > 30:
                return self._cleanup('gesture_timeout')
            if self.drag['finishing'] and now >= self.drag['finishing']:
                return self._cleanup('final_frame_timeout')
            point = self.root.query_pointer()
            actual = self._geometry()
            dims = (actual[2], actual[3])
            sent = self.drag['sent']
            if sent and dims != (sent[2], sent[3]):
                # WM/应用把尺寸夹到它自己的范围：以实际几何为准，避免状态机失配
                if dims != self.drag.get('adopted'):
                    self.drag['adopted'] = dims
                    self.log('adopt', sent=list(sent), actual=list(actual))
                self.drag['sent'] = actual
            if self.drag['finishing']:
                hide_at = self.drag.get('hide_at')
                if hide_at and now >= hide_at:
                    return self._cleanup('final_frame_ready')
                valid = self.cache.capture(self.parent)
                if valid and dims == (self.drag['sent'][2], self.drag['sent'][3]) \
                        and self.cache.content_dimensions == dims:
                    sample = self.cache.last_sample or {}
                    sig = (round(sample.get('mean', 0), 1), sample.get('min'), sample.get('max'))
                    if sig == self.drag.get('sig'):
                        stable = self.drag.get('stable', 0) + 1
                    else:
                        stable = 0
                    self.drag['sig'] = sig
                    self.drag['stable'] = stable
                    self._show(actual)
                    if stable >= 2 and not self.drag.get('hide_at'):
                        self._enforce_final(tuple(actual))
                        self.drag['hide_at'] = now + 0.15
                        self.log('final_settled', rectangle=list(actual), stable=stable, sample=sample)
                    return
                if self.cache.last_error:
                    raise RuntimeError(self.cache.last_error)
                return
            if not point.mask & X.Button1Mask:
                self._finish(point.root_x, point.root_y)
                return
            self.drag['target'] = resize_rect(self.drag['original'], self.drag['origin'],
                (point.root_x, point.root_y), direction)
            # 拖拽期用「活帧」刷新覆盖层：应用自身也在重排/播放预览，冻结帧会显得不同步（闪）
            if LIVE_FRAMES and now - self.drag.get('cap_at', 0) >= 0.06:
                self.drag['cap_at'] = now
                try:
                    self.cache.capture(self.parent)
                except Exception:
                    pass
            self._show(actual if dims else self.drag['target'])
            want = (self.drag['target'][2], self.drag['target'][3])
            last = self.drag.get('want')
            if want != last and now-self.drag['sent_at'] >= self.INTERVAL_REQUEST:
                self.drag['want'] = want
                self._request(self.drag['target'])
        except Exception as exc:
            self.log('resize_failure',error=str(exc))
            self._fallback(direction, 'resize_exception')

    def event(self, event):
        if self.drag and event.type == X.ButtonPress and event.detail == 1:
            self._cleanup('superseded_gesture')
        if self.drag:
            if event.type == X.KeyPress and event.detail == self.escape_key:
                self._request(self.drag['original'])
                self._cleanup('escape', escape_event=event)
                return
            if event.type == X.ButtonRelease and event.detail == 1:
                self._finish(event.root_x, event.root_y)
                return
            if event.type == X.MotionNotify:
                return  # Latest root pointer position is sampled once per tick.
            if event.type == X.MapNotify:
                allowed = {self.parent.id, self._ancestor().id}
                if self.preview is not None:
                    allowed.add(self.preview.id)
                allowed.update(w.id for w in self.children.values())
                if event.window.id not in allowed:
                    self._cleanup('another_window_mapped')
            elif event.type == X.PropertyNotify and event.window.id == self.root.id:
                if event.atom == self.atom('_NET_ACTIVE_WINDOW') and not self._foreground():
                    self._cleanup('active_window_changed')
            elif event.type in (X.UnmapNotify, X.DestroyNotify) and event.window.id == self.parent.id:
                self._cleanup('main_window_unavailable')
        super().event(event)

    def destroy(self):
        self._cleanup('detach')
        super().destroy()

    def run(self):
        try:
            while self.running:
                while self.d.pending_events():
                    event = self.d.next_event()
                    try:
                        self.event(event)
                    except Exception as exc:
                        self.log('event_error',error=str(exc))
                        if self.drag:
                            self._fallback(self.drag['direction'], 'event_exception')
                now = time.monotonic()
                if self.drag:
                    if now >= self.next_tick:
                        self._tick()
                        self.next_tick = max(now + self.INTERVAL, time.monotonic() + .001)
                elif now-self.last_scan > .25:
                    self.discover()
                    self.last_scan = now
                self.keepalive()
                if self.args.idle_timeout and now-self.last_seen > self.args.idle_timeout:
                    break
                timeout = max(0, min(.033, self.next_tick-time.monotonic())) if self.drag else .05
                if not self.d.pending_events():
                    select.select([self.d], [], [], timeout)
        finally:
            try:
                self.destroy()
                self.log('stop')
            finally:
                self.d.close()
                self.logfile.close()


if __name__ == '__main__':
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument('--paced-only', action='store_true')
    extra, remaining = options.parse_known_args()
    PREVIEW = not extra.paced_only
    sys.argv[1:] = remaining
    base.Grips = LiveGrips
    base.main()
