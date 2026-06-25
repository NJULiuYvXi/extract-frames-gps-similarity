#!/usr/bin/env python3
"""ffprobe / ffmpeg / cv2.cuda capability probing and small parse helpers.

- probe_frame_count / probe_video_dims : ffprobe queries on a video file.
- parse_resolution                     : "WxH" string -> (w, h) or None.
- probe_hwaccel                        : pick the best ffmpeg decode hwaccel
                                         for the fixed-interval mode.
- probe_cv2_cuda                       : whether OpenCV exposes a usable CUDA
                                         device for the adaptive ORB path.
"""

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from .imports import _try_import_cv2

RES_RE = re.compile(r"^\s*(\d+)\s*[x×*]\s*(\d+)\s*$", re.IGNORECASE)


def probe_frame_count(video_path: Path) -> int:
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-count_packets", "-show_entries", "stream=nb_read_packets",
                "-of", "csv=p=0", str(video_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return int(r.stdout.strip() or 0)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return 0


def probe_video_dims(video_path: Path):
    """Return (width, height) of the first video stream, or None."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0", str(video_path),
            ],
            capture_output=True, text=True, check=True,
        )
        w, h = r.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except (subprocess.CalledProcessError, ValueError,
            IndexError, FileNotFoundError):
        return None


def parse_resolution(s: str):
    if not s:
        return None
    m = RES_RE.match(s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


# --- ffmpeg decode hwaccel detection ----------------------------------------

def _list_ffmpeg_hwaccels() -> set:
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-hwaccels"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    out = set()
    for line in r.stdout.splitlines():
        line = line.strip()
        if line and not line.endswith(":"):
            out.add(line.lower())
    return out


def _has_nvidia_gpu() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        r = subprocess.run(
            ["nvidia-smi", "-L"], capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and "GPU" in r.stdout


def _has_dri_render_node() -> bool:
    for i in range(128, 192):
        if os.path.exists(f"/dev/dri/renderD{i}"):
            return True
    return False


def _vaapi_device_path() -> str:
    for i in range(128, 192):
        p = f"/dev/dri/renderD{i}"
        if os.path.exists(p):
            return p
    return "/dev/dri/renderD128"


def probe_hwaccel():
    """Decode hwaccel for ffmpeg (used by fixed-interval mode)."""
    available = _list_ffmpeg_hwaccels()
    if not available:
        return None
    system = platform.system()
    if system == "Darwin":
        candidates = [
            ("videotoolbox", ["-hwaccel", "videotoolbox"],
             "Apple VideoToolbox", lambda: True),
        ]
    elif system == "Linux":
        candidates = [
            ("cuda", ["-hwaccel", "cuda"],
             "NVIDIA CUDA / NVDEC", _has_nvidia_gpu),
            ("vaapi",
             ["-hwaccel", "vaapi", "-hwaccel_device", _vaapi_device_path()],
             "VA-API (AMD / Intel)", _has_dri_render_node),
            ("vdpau", ["-hwaccel", "vdpau"],
             "VDPAU (NVIDIA legacy)", _has_nvidia_gpu),
        ]
    elif system == "Windows":
        candidates = [
            ("cuda", ["-hwaccel", "cuda"],
             "NVIDIA CUDA / NVDEC", _has_nvidia_gpu),
            ("d3d11va", ["-hwaccel", "d3d11va"],
             "Direct3D 11 Video Acceleration", lambda: True),
            ("qsv", ["-hwaccel", "qsv"],
             "Intel Quick Sync Video", lambda: True),
            ("dxva2", ["-hwaccel", "dxva2"],
             "DirectX Video Acceleration 2", lambda: True),
        ]
    else:
        return None
    for name, args, desc, predicate in candidates:
        if name in available and predicate():
            return {"name": name, "args": args, "description": desc}
    return None


# --- cv2 CUDA detection (used by adaptive mode for ORB) ---------------------

def probe_cv2_cuda():
    """Return (available, info_string)."""
    cv2, np, err = _try_import_cv2()
    if cv2 is None:
        return False, f"opencv-python not installed ({err})"
    try:
        n = cv2.cuda.getCudaEnabledDeviceCount()
    except Exception:  # noqa: BLE001
        return False, "this OpenCV build has no CUDA module"
    if n <= 0:
        return False, "no CUDA-capable device usable by OpenCV"
    try:
        name = cv2.cuda.printCudaDeviceInfo  # presence check
        return True, f"cv2.cuda available ({n} device(s))"
    except Exception:  # noqa: BLE001
        return True, f"cv2.cuda available ({n} device(s))"
