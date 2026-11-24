#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Render the repository's original SVG diagrams and 3:4 social cards.

Requires the Ubuntu python3-gi, gir1.2-rsvg-2.0 and python3-cairo packages.
No application screenshots, brand artwork or private data are used.
"""
from html import escape
from pathlib import Path
import cairo
import gi

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg

OUT = Path(__file__).resolve().parents[1] / "docs/media"
PAPER, INK, MUTED = "#f3f1e9", "#161a1a", "#646962"
RED, GREEN, LINE = "#f62d53", "#13866d", "#d8dbd2"
WHITE = "#ffffff"
FONT = "'Noto Sans CJK SC','Source Han Sans SC',sans-serif"


def rect(x, y, w, h, fill, rx=0, stroke=None):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}"' + (f' stroke="{stroke}" stroke-width="2"' if stroke else '') + '/>')


def text(x, y, value, size=36, fill=INK, weight=400, anchor="start", spacing=0):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
            f'letter-spacing="{spacing}">{escape(value)}</text>')


def path(d, color=INK, width=4):
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>'


def icon(kind, x, y, color=INK, scale=1):
    shapes = {
        "screen": path("M4 6 H60 V44 H4 Z M23 57 H41 M32 44 V57", color),
        "window": path("M4 8 H60 V55 H4 Z M4 22 H60 M13 15 H15 M22 15 H24", color),
        "shield": path("M32 3 L56 13 V32 C56 48 32 61 32 61 C32 61 8 48 8 32 V13 Z M21 31 L29 39 L44 23", color),
        "gpu": path("M12 12 H52 V52 H12 Z M22 22 H42 V42 H22 Z M21 3 V12 M42 3 V12 M21 52 V61 M42 52 V61 M3 21 H12 M3 42 H12 M52 21 H61 M52 42 H61", color),
        "live": path("M8 15 H44 V49 H8 Z M44 26 L60 16 V48 L44 38 M25 25 L35 32 L25 39 Z", color),
        "sound": path("M7 26 H18 L32 13 V51 L18 39 H7 Z M43 21 C52 27 52 38 43 44 M51 10 C68 24 68 40 51 55", color),
        "check": path("M8 32 L24 48 L57 14", color, 6),
        "arrow": path("M5 32 H58 M45 18 L59 32 L45 46", color),
    }
    return f'<g transform="translate({x} {y}) scale({scale})">{shapes[kind]}</g>'


def mark(x, y, size=60):
    s = rect(x, y, size, size, RED, size * .25)
    s += path(f'M{x+size*.32} {y+size*.74} V{y+size*.27} H{x+size*.7} M{x+size*.32} {y+size*.49} H{x+size*.61}', WHITE, size*.085)
    return s


def brand(page, dark=False):
    c, m = (PAPER, "#a5ada7") if dark else (INK, MUTED)
    return (mark(96, 88) + text(180, 131, "FELIX LIVE COMPAT", 34, c, 700, spacing=1)
            + text(1344, 128, f"0{page} / 03", 28, m, anchor="end")
            + path("M96 185 H1344", "#363f3b" if dark else LINE, 2))


def footer(dark=False):
    c = "#a5ada7" if dark else MUTED
    line = "#363f3b" if dark else LINE
    return (path("M96 1740 H1344", line, 2)
            + text(96, 1803, "GitHub 搜索  Felix-Live-Compat", 34, PAPER if dark else INK, 600)
            + text(96, 1858, "社区兼容项目 · Felix Li · 2026.11", 28, c))


def svg(w, h, body, label, bg=PAPER):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}">'
            f'<title>{escape(label)}</title>{rect(0,0,w,h,bg)}{body}</svg>')


def save(name, data, png=True):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (name + ".svg")).write_text(data, encoding="utf-8")
    if png:
        handle = Rsvg.Handle.new_from_data(data.encode())
        _, width, height = handle.get_intrinsic_size_in_pixels()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(width), int(height))
        viewport = Rsvg.Rectangle()
        viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, width, height
        handle.render_document(cairo.Context(surface), viewport)
        surface.write_to_png(str(OUT / (name + ".png")))


def cover():
    b = brand(1)
    b += rect(96, 242, 328, 60, INK, 30) + text(260, 284, "Ubuntu 游戏直播", 30, PAPER, 500, "middle")
    b += text(90, 475, "Ubuntu 上，", 140, INK, 800)
    b += text(90, 651, "也能用", 140, INK, 800)
    b += text(90, 827, "直播伴侣。", 140, RED, 800)
    b += text(98, 927, "官方 Windows 客户端 × 开源兼容层", 42, MUTED, 500)
    # An original architecture illustration, deliberately not a fake screenshot.
    b += rect(96, 1010, 1248, 395, INK, 40)
    b += text(140, 1070, "从 Linux 画面，到官方客户端", 28, "#9ba8a0")
    for x, label, kind in [(145, "桌面 / 窗口", "screen"), (570, "兼容桥接", "gpu"), (995, "直播伴侣", "live")]:
        b += rect(x, 1110, 300, 205, "#252e29", 26, "#404d45")
        b += icon(kind, x+119, 1137, "#f3f1e9")
        b += text(x+150, 1280, label, 34, PAPER, 600, "middle")
    b += icon("arrow", 476, 1172, RED) + icon("arrow", 901, 1172, RED)
    b += text(140, 1370, "实现示意", 25, "#9ba8a0")
    b += icon("check", 96, 1470, GREEN, .68)
    b += text(157, 1506, "采集、录制、短时开播已实测", 46, INK, 700)
    b += text(98, 1588, "支持全屏与多窗口素材，保留 UnityCapture 回退。", 34, MUTED)
    b += text(98, 1652, "开源兼容层与安装工具；官方客户端另行下载。", 32, MUTED)
    b += footer()
    save("social-01-cover", svg(1440,1920,b,"Felix Live Compat：在 Ubuntu 使用官方 Windows 直播伴侣"))


def tests():
    b = brand(2)
    b += text(96, 337, "已完成", 112, INK, 800)
    b += text(96, 477, "实际链路测试。", 112, INK, 800)
    b += text(98, 569, "启动之后，继续验证画面、声音和推流。", 39, MUTED)
    cards = [
        (96, 655, "screen", "全屏采集", ["1920 × 1080", "动态桌面预览"], "系统授权后直接出画面"),
        (736, 655, "window", "窗口采集", ["多窗口 / 真实标题", "静止首帧 / 后台更新"], "取消、删除与关窗清理"),
        (96, 1075, "sound", "本地音画", ["720p30 视频", "48 kHz 双声道 AAC"], "录像解码核对测试画面与声音"),
        (736, 1075, "live", "短时开播", ["全屏约 33 秒", "窗口约 28 秒"], "隔离候选 · 伴侣推流端验证"),
    ]
    for x,y,kind,title,lines,note in cards:
        b += rect(x,y,608,378,WHITE,30,LINE)
        b += icon(kind,x+36,y+35,GREEN,.72)
        b += text(x+101,y+77,title,42,INK,700)
        b += rect(x+454,y+34,117,50,"#e3f2e9",25) + text(x+512,y+70,"已实测",25,GREEN,600,"middle")
        for i,line in enumerate(lines):b += text(x+38,y+169+i*57,line,35,INK,600)
        b += path(f'M{x+38} {y+271} H{x+570}',LINE,2)
        b += text(x+38,y+328,note,27,MUTED)
    b += text(98, 1542, "测试基线", 29, GREEN, 700)
    b += text(98, 1594, "Ubuntu 26.04 · GNOME Wayland / XWayland · RTX 4060", 31, INK, 500)
    b += text(98, 1650, "分阶段历史验收；观众端画质、长时直播仍待验证。", 30, MUTED)
    b += text(98, 1700, "适配官方客户端 13.3.5.564315535，详见仓库验收记录。", 28, MUTED)
    b += footer()
    save("social-02-tested", svg(1440,1920,b,"全屏、窗口、本地音画和短时推流的已验证范围"))


STEPS = [
    ("screen", "Ubuntu 桌面 / 窗口", "在伴侣里选择全屏或窗口素材"),
    ("shield", "系统授权 + PipeWire", "你决定允许共享哪块屏幕、哪扇窗口"),
    ("gpu", "DMA-BUF + WGC 兼容层", "GPU 缓冲传递，让伴侣读取 Linux 画面"),
    ("live", "官方 Windows 直播伴侣", "在 Felix-Proton 中完成预览、合成和编码"),
    ("arrow", "推流到抖音直播间", "短时全屏 / 窗口推流端已实测"),
]


def flow_card():
    b = brand(3,True)
    b += text(96, 329, "这条采集链路，", 94, PAPER, 800)
    b += text(96, 452, "如何跑起来？", 94, PAPER, 800)
    b += text(98, 542, "Linux 原生采集，接入官方客户端。", 39, "#acb8b0")
    for i,(kind,title,desc) in enumerate(STEPS):
        y=620+i*186
        b += text(98,y+59,f"0{i+1}",31,"#9ba8a0",600)
        b += rect(179,y,1165,151,"#29342d" if i!=2 else "#f62d53",27,"#405146" if i!=2 else None)
        b += icon(kind,215,y+43,PAPER,.91)
        b += text(310,y+61,title,41,PAPER,700)
        b += text(310,y+115,desc,30,"#c4d0c8" if i!=2 else WHITE)
        if i<4:b += path(f'M760 {y+158} V{y+178} M752 {y+171} L760 {y+179} L768 {y+171}',"#71877a",3)
    b += text(98, 1612, "无需采集卡 · 这条链路不经过虚拟摄像头", 36, PAPER, 600)
    b += text(98, 1676, "客户端界面通过 Wine / Proton 兼容运行。", 30, "#acb8b0")
    b += footer(True)
    save("social-03-flow",svg(1440,1920,b,"Ubuntu 原生采集到官方 Windows 直播伴侣的实现流程",INK))


def repo_graphics():
    b=mark(70,64,64)+text(157,110,"FELIX LIVE COMPAT",35,PAPER,700,spacing=1)
    b+=text(70,232,"让官方直播伴侣，在 Ubuntu 上工作。",65,PAPER,800)
    b+=text(73,310,"桌面与窗口共享 · 本地音画录制 · 已完成短时推流测试",32,"#bdc8c0")
    b+=rect(73,363,408,63,RED,31)+text(277,405,"开源兼容层 / 社区项目",27,WHITE,600,"middle")
    b+=text(1370,407,"Felix Li",30,"#bdc8c0",500,"end")
    save("readme-hero",svg(1440,485,b,"Felix Live Compat，Ubuntu 上的直播伴侣兼容方案",INK))
    b=text(62,112,"画面在 Linux 采集，直播在官方客户端完成。",48,INK,800)
    b+=text(64,176,"应用内选择素材 → Ubuntu 授权 → GPU 缓冲桥接 → 预览、合成与编码 → 推流",28,MUTED)
    labels=[("screen","Ubuntu 画面","桌面 / 任意可共享窗口"),("shield","系统授权","Portal + PipeWire"),("gpu","兼容桥接","DMA-BUF + WGC"),("live","直播伴侣","官方客户端 + Felix-Proton"),("arrow","抖音直播间","伴侣推流端已短时实测")]
    for i,(kind,title,desc) in enumerate(labels):
        x=62+i*266;bg=INK if i==2 else WHITE;fg=PAPER if i==2 else INK
        b+=rect(x,254,250,266,bg,24,None if i==2 else LINE)
        b+=icon(kind,x+94,287,RED if i==2 else GREEN)
        b+=text(x+125,403,title,33,fg,700,"middle")
        b+=text(x+125,461,desc,18,"#b4c2b8" if i==2 else MUTED,500,"middle")
        if i<4:b+=path(f'M{x+253} 379 H{x+263} M{x+258} 374 L{x+263} 379 L{x+258} 384',RED,3)
    b+=text(64,596,"此处为直接采集链路；UnityCapture 作为独立回退保留。",28,MUTED)
    b+=text(64,645,"界面仍通过 Wine / Proton 兼容运行，原生 UI 体验持续改进中。",25,MUTED)
    save("capture-flow",svg(1440,702,b,"Linux Portal、PipeWire、DMA-BUF、WGC 与官方客户端的采集流程"))


if __name__ == "__main__":
    cover(); tests(); flow_card(); repo_graphics()
    print(f"Rendered 5 SVG + 5 PNG assets in {OUT}")
