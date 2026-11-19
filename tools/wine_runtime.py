# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Build the matched Wine client/server modules for the pinned runner."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from assets import obtain


ROOT = Path(__file__).resolve().parents[1]
PATCHES = ROOT / "patches/wine"
PATCH_SERIES = (
    "0066-ntdll-Implement-replacing-file-completion-ports.patch",
    "0067-winex11-Preserve-opt-in-ARGB-formats-for-other-process-surfaces.patch",
    "0068-winex11-Derive-alpha-input-shapes-from-composed-destination.patch",
    "0069-winex11-Opt-in-to-native-maximized-caption-moves.patch",
    "0070-winex11-Keep-profiled-layered-decoration-windows-out-of-fullscreen.patch",
    "0071-winex11-Opt-in-to-an-application-specific-WM-instance.patch",
)
WINE_SOURCE = "felix-proton-uu-test.1-modified-wine-source/wine"
SDK = ("registry.gitlab.steamos.cloud/proton/steamrt4/sdk/x86_64@sha256:"
       "6c1789cad862fd8ed9d46d71bbf8752bb7cb2336ab5e9680c0f0e3e7c88d77f1")
MODULES = {
    "wineserver": "files/bin/wineserver",
    "ntdll.so": "files/lib/wine/x86_64-unix/ntdll.so",
    "wow64.dll": "files/lib/wine/x86_64-windows/wow64.dll",
    "winex11.so": "files/lib/wine/x86_64-unix/winex11.so",
}


def build_wine_modules(output, asset_dir):
    with tempfile.TemporaryDirectory(prefix="felix-live-wine-") as transaction:
        work = Path(transaction)
        with obtain("wine_source", asset_dir) as release:
            subprocess.run(["tar", "--zstd", "-xf", release, "--no-same-owner",
                            "--strip-components=1", "-C", work, WINE_SOURCE], check=True)
        for name in PATCH_SERIES:
            subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1",
                            "-d", work / "wine", "-i", PATCHES / name], check=True)
        subprocess.run(["docker", "run", "--rm", "--pull", "never", "--network", "none",
                        "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL",
                        "--security-opt", "no-new-privileges",
                        "--user", f"{os.getuid()}:{os.getgid()}",
                        "-v", f"{work}:/work", "-v", f"{ROOT / 'tools/build_wine.sh'}:/build-wine.sh:ro",
                        SDK, "bash", "/build-wine.sh"], check=True)
        output.mkdir(parents=True, exist_ok=True)
        for name in MODULES:
            shutil.copy2(work / "artifacts" / name, output / name)


def install_wine_modules(payload, runner):
    for name, relative in MODULES.items():
        destination = runner / relative
        destination.resolve(strict=True).relative_to(runner)
        temporary = destination.with_suffix(".felix-new")
        shutil.copy2(payload / "wine-runtime" / name, temporary)
        os.replace(temporary, destination)
