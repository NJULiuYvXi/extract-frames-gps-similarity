#!/usr/bin/env python3
"""DJI .SRT sidecar parsing -> per-frame GPS (latitude, longitude, altitude).

The DJI subtitle stream stores one block per video frame; ``SrtCnt`` is the
1-based frame index used to align GPS with the extracted JPEGs.
"""

import re
from pathlib import Path

SRT_BLOCK_RE = re.compile(
    r"SrtCnt\s*:\s*(\d+)"
    r".*?\[\s*latitude\s*:\s*([-\d.]+)\s*\]"
    r"\s*\[\s*longitude\s*:\s*([-\d.]+)\s*\]"
    r"\s*\[\s*altitude\s*:\s*([-\d.]+)\s*\]",
    re.DOTALL,
)


def parse_srt(srt_path: Path):
    try:
        text = srt_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    out = {}
    for m in SRT_BLOCK_RE.finditer(text):
        idx = int(m.group(1))
        out[idx] = (float(m.group(2)), float(m.group(3)), float(m.group(4)))
    return out


def find_srt(video_path: Path):
    for ext in (".SRT", ".srt", ".Srt"):
        p = video_path.with_suffix(ext)
        if p.exists():
            return p
    return None
