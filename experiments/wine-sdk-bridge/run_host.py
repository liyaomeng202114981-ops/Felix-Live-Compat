#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Bounded official SDK query, using only an existing private evidence prefix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--case', type=Path, required=True)
parser.add_argument('--result', default='query-result.json')
parser.add_argument('--probe-only', action='store_true')
parser.add_argument('--trace-seh', action='store_true')
parser.add_argument('--empty-sign-info', action='store_true')
parser.add_argument('--client-product-config', action='store_true')
parser.add_argument('--preview-test', action='store_true')
args = parser.parse_args()
root = args.root.resolve(strict=True)
case = args.case.resolve()
if 'evidence' not in root.parts or 'evidence' not in case.parts:
    parser.error('Only private evidence paths are accepted; never use a daily installation')
if Path(args.result).name != args.result:
    parser.error('Result must be a filename')
case.mkdir(mode=0o700, parents=True, exist_ok=True)
app = root / 'prefix/pfx/drive_c/Program Files (x86)/webcast_mate/13.3.5.564315535'
host = case / 'host'
host.mkdir(exist_ok=True)
for p in app.iterdir():
    target = host / p.name
    if target.exists() or p.name == 'resources':
        continue
    if p.is_file():
        os.link(p, target)
    else:
        target.symlink_to(p)
resources = host / 'resources/app'
resources.mkdir(parents=True, exist_ok=True)
for src, dst in [('probe.js' if args.probe_only else 'query.js', 'index.js'),
                 ('sdk-loader.js', 'sdk-loader.js'), ('product-context.js', 'product-context.js')]:
    shutil.copy2(Path(__file__).parent / src, resources / dst)
(resources / 'package.json').write_text('{"name":"felix-sdk-query","version":"0.0.1","main":"index.js"}')
state = case / 'sdk-state'
state.mkdir(exist_ok=True)
if args.preview_test:
    for phase in ['a','b']:
        pixels = bytearray()
        for y in range(180):
            for x in range(320):
                red = (x < 160) == (phase == 'a')
                rgb = (220,35,45) if red else (35,195,85)
                if 12 <= y < 30 and 12 <= x < 70:
                    rgb = (40,100,240)
                pixels.extend(rgb[::-1])
        header = b'BM' + struct.pack('<IHHI',54+len(pixels),0,0,54)
        dib = struct.pack('<IiiHHIIiiII',40,320,-180,1,24,0,len(pixels),2835,2835,0,0)
        (state / f'fixture-{phase}.bmp').write_bytes(header + dib + pixels)
result = case / args.result
result.unlink(missing_ok=True)
unit = 'felix-sdk-query-' + hashlib.sha256(str(result).encode()).hexdigest()[:12]
def win(p):
    return 'Z:' + str(p).replace('/', '\\')
settings = {
    'FELIX_SDK_ADDON':win(app / 'resources/app/app.content/node_modules/@byted/mediasdk-client/lib/MediaSDK_Client.node'),
    'FELIX_SDK_BUNDLE':win(app / 'resources/app/app.content/main.js'),
    'FELIX_SDK_RESULT':win(result), 'FELIX_SDK_INITIALIZE':'1',
    'FELIX_SDK_STATE':win(state), 'FELIX_SDK_INSTALL':win(app),
    'PRESSURE_VESSEL_FILESYSTEMS_RW':str(case) + ':' + str(root),
    'WINEDEBUG':'-all', 'PROTON_LOG':'0', 'PROTON_NVIDIA_NVENC':'1', 'PROTON_FORCE_NVAPI':'1',
    'WINEDLLOVERRIDES':'d3d11=n;graphicscapture=n;winemenubuilder.exe=d'}
if args.probe_only:
    settings['ELECTRON_RUN_AS_NODE'] = '1'
if args.trace_seh:
    settings['WINEDEBUG'] = '+seh,+loaddll'
if args.empty_sign_info:
    settings['FELIX_SDK_EMPTY_SIGN_INFO'] = '1'
if args.client_product_config:
    settings['FELIX_SDK_CLIENT_PRODUCT'] = '1'
if args.preview_test:
    settings['FELIX_SDK_CLIENT_PRODUCT'] = '1'
    settings['FELIX_SDK_PREVIEW_TEST'] = '1'
for name in ['DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS']:
    if name in os.environ:
        settings[name] = os.environ[name]
command = ['systemd-run','--user','--collect',f'--unit={unit}','--service-type=exec',
    '--property=RuntimeMaxSec=22s','--property=TimeoutStopSec=3s','--property=KillMode=control-group',
    f'--property=StandardOutput=append:{case}/host.log',f'--property=StandardError=append:{case}/host.log']
command += [f'--setenv={k}={v}' for k,v in settings.items()]
command += ['--',str(root / 'shorin-proton-wrapper'),'--prefix',str(root / 'prefix'),
    '--runner',str(root / 'runner/proton'),str(host / '直播伴侣.exe'),win(resources / 'index.js')]
def interrupted(signum, _frame):
    raise SystemExit(128 + signum)
signal.signal(signal.SIGTERM, interrupted)
try:
    subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            data = json.loads(result.read_text())
            if data.get('complete'):
                print(json.dumps(data, ensure_ascii=False))
                break
            time.sleep(.1)
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(.1)
    else:
        raise TimeoutError('SDK host did not return within 20 seconds; inspect private host.log')
finally:
    subprocess.run(['systemctl','--user','stop',unit],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
