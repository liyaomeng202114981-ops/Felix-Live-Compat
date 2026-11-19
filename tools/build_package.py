#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Build the capture binaries and assemble a Linux compatibility kit locally."""

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from assets import obtain
from wine_runtime import MODULES, build_wine_modules


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "src/wgc-compat"
DXVK = ("felix-proton-uu-test-0.1.0-test.1/"
        "files/lib/wine/dxvk/x86_64-windows/d3d11.dll")
PAYLOAD = ("d3d11.dll", "felix_wgc.dll", "inapp_actions.exe", "felix-wgc-window.exe",
           "window-stream", "vulkan/libfelixwgc.so", "vulkan/VkLayer_felix_wgc.json")
PACKAGE_FILES = ("README.md", "LICENSE", "THIRD_PARTY.md", "assets.json",
                 "compatibility.json", "tools", "src", "docs", "patches")


def build(payload, asset_dir, sysroot):
    with tempfile.TemporaryDirectory(prefix="felix-live-build-") as directory:
        temporary = Path(directory)
        base = temporary / "dxvk.dll"
        with obtain("runner", asset_dir) as runner, base.open("wb") as output:
            subprocess.run(["tar", "--zstd", "-xOf", runner, DXVK], stdout=output, check=True)
        subprocess.run(["/usr/bin/python3", "-B", CAPTURE / "build.py", base, temporary,
                        "--in-app"], check=True)
        arguments = ["sh", CAPTURE / "dmabuf/build.sh", temporary / "window-stream"]
        if sysroot is not None:
            arguments.append(sysroot)
        subprocess.run(arguments, check=True)
        subprocess.run(["sh", CAPTURE / "dmabuf/build_layer.sh", temporary / "vulkan"], check=True)
        for name in PAYLOAD:
            destination = payload / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temporary / name, destination)
    build_wine_modules(payload / "wine-runtime", asset_dir)
    names = (*PAYLOAD, *(f"wine-runtime/{name}" for name in MODULES))
    digests = [f"{hashlib.sha256((payload / name).read_bytes()).hexdigest()}  {name}"
               for name in names]
    (payload / "SHA256SUMS").write_text("\n".join(digests) + "\n", encoding="ascii")


def package(output, payload):
    def remove_cache(member):
        if "__pycache__" in Path(member.name).parts:
            return None
        return member

    with tarfile.open(output, mode="x:gz") as archive:
        for name in PACKAGE_FILES:
            archive.add(ROOT / name, arcname=f"Felix-Live-Compat/{name}", filter=remove_cache)
        archive.add(payload, arcname="Felix-Live-Compat/payload")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=lambda path: Path(path).resolve(), required=True)
    parser.add_argument("--assets", type=lambda path: Path(path).resolve(strict=True))
    parser.add_argument("--sysroot", type=lambda path: Path(path).resolve(strict=True))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="felix-live-kit-") as directory:
        payload = Path(directory) / "payload"
        build(payload, args.assets, args.sysroot)
        package(args.output, payload)
    print(args.output)


if __name__ == "__main__":
    main()
