#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Run own app using a read-only installed Linux Electron distribution."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--electron-base', type=Path,
                    default=Path('/opt/apps/com.douyin.otohime/files'))
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--self-test', action='store_true')
parser.add_argument('--app-dir', type=Path, default=Path(__file__).parent)
args = parser.parse_args()
base = args.electron_base.resolve(strict=True)
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True, mode=0o700)
with tempfile.TemporaryDirectory(prefix='native-demo-', dir=output) as directory:
    runtime = Path(directory)
    for source in base.iterdir():
        if source.name in ('resources', 'douyin'):
            continue
        (runtime / source.name).symlink_to(source)
    binary = runtime / 'electron'
    try:
        os.link(base / 'douyin', binary)
    except OSError:
        shutil.copy2(base / 'douyin', binary)
    app = runtime / 'resources/app'
    app.mkdir(parents=True)
    (app / 'package.json').write_text('{"name":"felix-native-preview-demo","version":"0.0.1","main":"main.js"}\n')
    for name in ('main.js', 'preload.js', 'index.html', 'producer.py'):
        source = args.app_dir.resolve(strict=True) / name
        if source.is_file():
            shutil.copy2(source, app / name)
    options = ['--self-test'] if args.self_test else []
    command = [str(binary), '--ozone-platform=wayland',
               '--user-data-dir=' + str(runtime / 'profile'), *options]
    run = subprocess.run(command, env=os.environ | {'FELIX_DEMO_OUTPUT': str(output)})
    raise SystemExit(run.returncode)
