#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Transparent resize grips and move strip for the official client window."""
import argparse, fcntl, json, os, select, signal, time
from pathlib import Path
from Xlib import X, Xatom, Xcursorfont, display, error, protocol

MAIN_CLASS = "直播伴侣".encode()

def layout(width, height, full=False, maximized=False):
    # 顶部移动条避开右侧窗口控件；缩放手柄贴内容边缘。
    boxes = {'move': (120, 4, max(1, width-120-260), 36, 8)}
    if maximized: return boxes
    t, c = 7, 14
    if not full:
        boxes['bottom'] = (c, height-t, max(1,width-2*c),t,5)
        return boxes
    boxes.update({
        'top_left': (0,0,c,c,0), 'top': (60,0,max(1,width-60-300),t,1),
        'top_right': (width-c,0,c,c,2), 'right': (width-t,c,t,max(1,height-2*c),3),
        'bottom_right': (width-c,height-c,c,c,4),
        'bottom': (c,height-t,max(1,width-2*c),t,5),
        'bottom_left': (0,height-c,c,c,6), 'left': (0,c,t,max(1,height-2*c),7)})
    return boxes


class Grips:
    def __init__(self, args):
        self.args=args; self.d=display.Display(); self.root=self.d.screen().root
        self.atoms={}; self.anchor=None; self.anchor_identity=None; self.parent=None; self.identity=None; self.children={}; self.directions={}; self.boxes={}
        self.original_min=None; self.applied_min=None; self.watched_pid=None; self.last_keepalive=0
        self.last_geometry=None; self.last_scan=0; self.pending=None; self.last_click=None
        self.running=True; self.last_seen=time.monotonic(); self.logfile=open(args.log,'a',buffering=1)
        self.cursors={}; self.font=self.d.open_font('cursor')
        names=[Xcursorfont.top_left_corner,Xcursorfont.top_side,Xcursorfont.top_right_corner,
               Xcursorfont.right_side,Xcursorfont.bottom_right_corner,Xcursorfont.bottom_side,
               Xcursorfont.bottom_left_corner,Xcursorfont.left_side,Xcursorfont.fleur]
        for direction, glyph in enumerate(names):
            self.cursors[direction]=self.font.create_glyph_cursor(self.font,glyph,glyph+1,(0,0,0),(65535,65535,65535))
        self.d.set_error_handler(self.xerror)
        self.root.change_attributes(event_mask=X.PropertyChangeMask|X.SubstructureNotifyMask)
        self.log('start',display=self.d.get_display_name(),full=args.full)
    def log(self,event,**data):
        self.logfile.write(json.dumps({'time':time.time(),'event':event,**data},ensure_ascii=False)+'\n')
    def xerror(self,err,request):
        # Windows may vanish between discovery and attachment. The next scan recovers.
        if not isinstance(err,(error.BadWindow,error.BadDrawable)): self.log('x_error',kind=type(err).__name__)
    def atom(self,name):
        if name not in self.atoms:self.atoms[name]=self.d.intern_atom(name)
        return self.atoms[name]
    def prop(self,w,name,typ=X.AnyPropertyType):
        try:
            p=w.get_full_property(self.atom(name),typ)
            return p.value if p else None
        except (error.BadWindow,error.BadDrawable): return None
    def qualify(self,w):
        try:
            cls=self.prop(w,'WM_CLASS')
            if cls is None: return None
            if isinstance(cls,(bytes,bytearray)): blob=bytes(cls)
            else: blob=b' '.join(bytes(x) for x in cls if isinstance(x,(bytes,bytearray)))
            if not blob or MAIN_CLASS not in blob: return None
            transient=w.get_wm_transient_for()
            if transient and transient.id: return None
            kind=self.prop(w,'_NET_WM_WINDOW_TYPE',Xatom.ATOM)
            if kind is not None and len(kind) and self.atom('_NET_WM_WINDOW_TYPE_NORMAL') not in kind: return None
            g=w.get_geometry()
            if g.width<800 or g.height<500: return None
            hints=self.prop(w,'WM_NORMAL_HINTS',Xatom.WM_SIZE_HINTS)
            if hints is not None and len(hints)>=9 and (int(hints[7]) or int(hints[8])):
                return None  # 固定尺寸窗口（companion 镜像窗等）
            return ('live', hex(w.id))
        except (OSError,ValueError,IndexError,error.BadWindow):
            return None

    def keepalive(self):
        # 客户端隐藏在托盘/游戏时仍保持 helper 存活
        now=time.monotonic()
        if now-self.last_keepalive<5:return
        self.last_keepalive=now
        needle=MAIN_CLASS
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                if p.stat().st_uid!=os.getuid():continue
                cmd=(p/'cmdline').read_bytes()
                if needle not in cmd:continue
                env=dict(x.split(b'=',1) for x in (p/'environ').read_bytes().split(b'\0') if b'=' in x)
                prefix = self.args.root.encode()
                if prefix in env.get(b'STEAM_COMPAT_DATA_PATH',b'') or prefix in env.get(b'WINEPREFIX',b''):
                    self.last_seen=now;return
            except (OSError,ValueError,IndexError):continue

    def ensure_min_size(self):
        # 只记录应用自己的最小尺寸，不再替应用写死下限（不同应用下限不同，交给 WM/应用自己决定）。
        if not self.parent:return
        current=self.prop(self.parent,'WM_NORMAL_HINTS',Xatom.WM_SIZE_HINTS)
        hints=list(map(int,current)) if current is not None else [0]*18
        hints += [0]*max(0,18-len(hints))
        if self.original_min is None:self.original_min=(bool(hints[0]&16),hints[5],hints[6])
    def restore_min_size(self):
        if not self.parent or self.original_min is None:return
        try:
            current=self.prop(self.parent,'WM_NORMAL_HINTS',Xatom.WM_SIZE_HINTS)
            if current is None:return
            hints=list(map(int,current))
            if len(hints)>=7 and hints[0]&16 and tuple(hints[5:7])==self.applied_min:
                had_min,w,h=self.original_min
                if not had_min:hints[0]&=~16
                hints[5:7]=[w,h]
                self.parent.change_property(Xatom.WM_NORMAL_HINTS,Xatom.WM_SIZE_HINTS,32,hints)
        except error.BadWindow:pass
    def destroy(self):
        self.restore_min_size()
        for w in self.children.values():
            try:w.destroy()
            except error.BadWindow:pass
        if self.parent:self.log('detach',window=hex(self.parent.id))
        self.children={};self.directions={};self.boxes={};self.parent=None;self.identity=None;self.last_geometry=None;self.pending=None;self.last_click=None;self.original_min=None;self.applied_min=None
        self.d.flush()
    def discover(self):
        candidates=self.prop(self.root,'_NET_CLIENT_LIST_STACKING',Xatom.WINDOW)
        windows=[self.d.create_resource_object('window',int(x)) for x in candidates] if candidates is not None else []
        if self.parent and all(w.id!=self.parent.id for w in windows):windows.append(self.parent)
        if self.anchor:
            if self.qualify(self.anchor)==self.anchor_identity:windows=[self.anchor]
            else:self.anchor=None;self.anchor_identity=None
        for w in reversed(windows):
            ident=self.qualify(w)
            if not ident:continue
            try:
                attrs=w.get_attributes();g=w.get_geometry()
                states=self.prop(w,'_NET_WM_STATE',Xatom.ATOM)
                states=set(map(int,states)) if states is not None else set()
                if attrs.map_state!=X.IsViewable or g.width<960 or g.height<540 or self.atom('_NET_WM_STATE_FULLSCREEN') in states or self.atom('_NET_WM_STATE_HIDDEN') in states:continue
                if self.anchor is None:self.anchor=w;self.anchor_identity=ident
                if not self.parent or self.parent.id!=w.id or self.identity!=ident:
                    self.destroy();self.parent=w;self.identity=ident
                    w.change_attributes(event_mask=X.StructureNotifyMask|X.PropertyChangeMask)
                    self.ensure_min_size()
                    self.log('attach',window=hex(w.id),pid=ident[0])
                self.last_seen=time.monotonic()
                maximized=self.atom('_NET_WM_STATE_MAXIMIZED_VERT') in states and self.atom('_NET_WM_STATE_MAXIMIZED_HORZ') in states
                state=(g.width,g.height,maximized)
                if state!=self.last_geometry:self.update(*state)
                return
            except error.BadWindow:continue
        if self.parent:self.destroy()
    def update(self,width,height,maximized):
        boxes=layout(width,height,self.args.full,maximized)
        for name in list(self.children):
            if name not in boxes:
                w=self.children.pop(name);self.directions.pop(w.id,None);self.boxes.pop(name,None);w.destroy()
        for name,(x,y,w,h,direction) in boxes.items():
            if name not in self.children:
                child=self.parent.create_window(x,y,w,h,0,0,X.InputOnly,X.CopyFromParent,
                    event_mask=X.StructureNotifyMask,
                    cursor=self.cursors[direction])
                child.grab_button(1,X.AnyModifier,False,X.ButtonPressMask|X.ButtonReleaseMask|X.PointerMotionMask,X.GrabModeAsync,X.GrabModeAsync,X.NONE,X.NONE)
                child.set_wm_name('WeGame mouse grip: '+name)
                self.children[name]=child;self.directions[child.id]=direction
                child.map();child.configure(stack_mode=X.Above)
            elif self.boxes.get(name)!=(x,y,w,h):self.children[name].configure(x=x,y=y,width=w,height=h)
            self.boxes[name]=(x,y,w,h)
        first_layout=self.last_geometry is None
        self.last_geometry=(width,height,maximized);self.d.flush()
        if first_layout or self.args.debug:self.log('layout',window=hex(self.parent.id),width=width,height=height,maximized=maximized,children={k:hex(w.id) for k,w in self.children.items()})
    def message(self,name,data):
        event=protocol.event.ClientMessage(window=self.parent,client_type=self.atom(name),data=(32,data))
        self.root.send_event(event,event_mask=X.SubstructureRedirectMask|X.SubstructureNotifyMask)
    def begin_drag(self,event,direction):
        if not self.parent or self.qualify(self.parent)!=self.identity:return
        point=self.root.query_pointer()
        if not point.mask & X.Button1Mask:return
        self.ensure_min_size()
        self.d.ungrab_pointer(event.time)
        self.message('_NET_ACTIVE_WINDOW',[1,event.time,0,0,0])
        self.message('_NET_WM_MOVERESIZE',[event.root_x,event.root_y,direction,1,1])
        self.d.flush();self.log('drag',direction=direction,x=event.root_x,y=event.root_y,window=hex(self.parent.id))
    def event(self,e):
        if e.type==X.ButtonPress: self.log('press',window=hex(e.window.id),x=e.root_x,y=e.root_y,detail=e.detail)
        if e.type==X.ButtonPress and e.window.id in self.directions:
            if e.detail!=1:return
            direction=self.directions[e.window.id]
            if direction==8:
                previous=self.last_click
                if previous and (e.time-previous[0]) & 0xffffffff < 350 and abs(e.root_x-previous[1])<5 and abs(e.root_y-previous[2])<5:
                    self.d.ungrab_pointer(e.time)
                    self.message('_NET_WM_STATE',[2,self.atom('_NET_WM_STATE_MAXIMIZED_VERT'),self.atom('_NET_WM_STATE_MAXIMIZED_HORZ'),1,0])
                    self.d.flush();self.last_click=None;self.pending=None;self.log('toggle_maximize');return
                self.pending=e;self.last_click=(e.time,e.root_x,e.root_y)
            else:self.begin_drag(e,direction)
        elif e.type==X.MotionNotify and self.pending:
            if not e.state & X.Button1Mask:self.pending=None;return
            p=self.pending
            if abs(e.root_x-p.root_x)+abs(e.root_y-p.root_y)>=4:
                self.pending=None;self.last_click=None;self.begin_drag(p,8)
        elif e.type==X.ButtonRelease:
            self.pending=None
        elif e.type==X.UnmapNotify and self.parent and e.window.id==self.parent.id:
            self.destroy()
        elif e.type==X.DestroyNotify:
            if self.anchor and e.window.id==self.anchor.id:self.anchor=None;self.anchor_identity=None
            if e.window.id in self.directions or (self.parent and e.window.id==self.parent.id):self.destroy()
        elif e.type==X.ConfigureNotify and self.parent and e.window.id==self.parent.id:
            self.last_scan=0
    def run(self):
        try:
            while self.running:
                while self.d.pending_events():self.event(self.d.next_event())
                now=time.monotonic()
                if now-self.last_scan>.25:self.discover();self.last_scan=now
                self.keepalive()
                if self.args.idle_timeout and now-self.last_seen>self.args.idle_timeout:break
                select.select([self.d],[],[],.05)
        finally:
            self.destroy();self.log('stop');self.d.close();self.logfile.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--full',action='store_true');p.add_argument('--debug',action='store_true');p.add_argument('--root',required=True);p.add_argument('--log',required=True);p.add_argument('--lock',required=True);p.add_argument('--idle-timeout',type=float,default=0)
    a=p.parse_args();Path(a.log).parent.mkdir(parents=True,exist_ok=True)
    lock=open(a.lock,'a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    logpath=Path(a.log)
    if logpath.exists() and logpath.stat().st_size>1024*1024:logpath.replace(str(logpath)+'.1')
    g=Grips(a)
    for signum in (signal.SIGINT,signal.SIGTERM):signal.signal(signum,lambda *_:setattr(g,'running',False))
    g.run()
if __name__=='__main__':main()
