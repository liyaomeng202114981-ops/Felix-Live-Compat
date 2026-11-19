# SPDX-License-Identifier: BSD-3-Clause
# Copyright 2026 Felix Li, with OpenAI Codex assistance.
"""Obtain the pinned Felix-Proton runner and launcher separately from this kit."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.request


LOCK = Path(__file__).resolve().parents[1] / "assets.json"


def verify(path, asset):
    with path.open("rb") as stream:
        if path.stat().st_size > asset["max_bytes"]:
            raise ValueError(f"Oversized asset: {asset['filename']}")
        if hashlib.file_digest(stream, "sha256").hexdigest() != asset["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {asset['filename']}")
    return path


@contextmanager
def obtain(key, asset_dir):
    asset = json.loads(LOCK.read_text(encoding="utf-8"))[key]
    if asset_dir is not None:
        yield verify(asset_dir / asset["filename"], asset)
        return
    with tempfile.TemporaryDirectory(prefix="felix-live-asset-") as temporary:
        destination = Path(temporary) / asset["filename"]
        with urllib.request.urlopen(asset["url"], timeout=60) as response, destination.open("wb") as output:
            count = 0
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > asset["max_bytes"]:
                    raise ValueError(f"Oversized asset: {asset['filename']}")
                output.write(chunk)
        yield verify(destination, asset)
