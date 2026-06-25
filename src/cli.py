#!/usr/bin/env python3
"""Headless command-line interface (the former ``--cli`` block of main()).

Usage (unchanged from the single-file version)::

  --cli fixed    INPUT OUTPUT [INTERVAL] [WxH|-] [JPEG_Q] [--gpu]
                 [--crop WxH] [--grid NxN] [--focal MM] [--threads N]
  --cli adaptive INPUT OUTPUT [TARGET%] [TOL%] [ORB|SIFT] [WxH|-] [JPEG_Q]
                 [--cv2-cuda] [--feat-side N] [--crop WxH] [--grid NxN]
                 [--focal MM] [--threads N]
"""

import sys
import threading
from pathlib import Path

from features.grid_split.grid_split import parse_grid

from src.core.pipeline import process_all
from src.core.probe import parse_resolution, probe_hwaccel


def main():
    """Parse and run the CLI. Expects ``--cli`` somewhere in sys.argv."""
    args = [a for a in sys.argv[1:] if a != "--cli"]
    use_gpu = "--gpu" in args
    prefer_cuda = "--cv2-cuda" in args
    feat_side = 720
    focal_length = 24.0
    thread_count = 1
    if "--feat-side" in args:
        i = args.index("--feat-side")
        feat_side = int(args[i + 1])
        del args[i:i + 2]
    if "--focal" in args:
        i = args.index("--focal")
        focal_length = float(args[i + 1])
        del args[i:i + 2]
    if "--threads" in args:
        i = args.index("--threads")
        thread_count = max(1, int(args[i + 1]))
        del args[i:i + 2]
    crop = None
    if "--crop" in args:
        i = args.index("--crop")
        crop = parse_resolution(args[i + 1])
        if crop is None:
            print(f"Invalid --crop value: {args[i + 1]!r} "
                  "(use WxH, e.g. 1920x1080)")
            sys.exit(2)
        del args[i:i + 2]
    grid_n = None
    if "--grid" in args:
        i = args.index("--grid")
        grid_n = parse_grid(args[i + 1])
        if grid_n is None and args[i + 1].lower() not in ("off", "-"):
            print(f"Invalid --grid value: {args[i + 1]!r} "
                  "(use NxN, e.g. 2x2 or 3x3)")
            sys.exit(2)
        del args[i:i + 2]
    args = [a for a in args
            if a not in ("--gpu", "--cv2-cuda")]

    if not args:
        print("Usage:\n"
              "  --cli fixed    INPUT OUTPUT [INTERVAL] [WxH|-] [JPEG_Q] "
              "[--gpu] [--crop WxH] [--grid NxN] [--focal MM] "
              "[--threads N]\n"
              "  --cli adaptive INPUT OUTPUT [TARGET%] [TOL%] "
              "[ORB|SIFT] [WxH|-] [JPEG_Q] [--cv2-cuda] [--feat-side N] "
              "[--crop WxH] [--grid NxN] [--focal MM] [--threads N]")
        sys.exit(2)

    sub = args[0].lower()
    rest = args[1:]
    cancel = threading.Event()

    def cli_progress(cur, total):
        if total > 0:
            sys.stdout.write(
                f"\rProgress: {cur}/{total} ({100.0*cur/total:5.1f}%)   "
            )
            sys.stdout.flush()

    if sub == "fixed":
        if len(rest) < 2:
            print("Need INPUT OUTPUT for fixed mode.")
            sys.exit(2)
        in_dir = Path(rest[0]); out_dir = Path(rest[1])
        interval = int(rest[2]) if len(rest) > 2 else 1
        res_arg = rest[3] if len(rest) > 3 else "-"
        quality = int(rest[4]) if len(rest) > 4 else 2
        resolution = (None if res_arg in ("-", "", "original")
                      else parse_resolution(res_arg))
        hwaccel = probe_hwaccel() if use_gpu else None
        try:
            process_all(
                in_dir, out_dir, "fixed", interval, resolution, crop,
                grid_n, quality,
                hwaccel, 0.0, 0.0, "ORB", False, 720, focal_length,
                thread_count,
                lambda m: print(m, flush=True), cli_progress, cancel,
            )
        finally:
            print()
        return

    if sub == "adaptive":
        if len(rest) < 2:
            print("Need INPUT OUTPUT for adaptive mode.")
            sys.exit(2)
        in_dir = Path(rest[0]); out_dir = Path(rest[1])
        target_pct = float(rest[2]) if len(rest) > 2 else 70.0
        tol_pct = float(rest[3]) if len(rest) > 3 else 5.0
        detector = (rest[4].upper() if len(rest) > 4 else "ORB")
        res_arg = rest[5] if len(rest) > 5 else "-"
        quality = int(rest[6]) if len(rest) > 6 else 2
        resolution = (None if res_arg in ("-", "", "original")
                      else parse_resolution(res_arg))
        try:
            process_all(
                in_dir, out_dir, "adaptive", 1, resolution, crop, grid_n,
                quality,
                None, target_pct / 100.0, tol_pct / 100.0,
                detector, prefer_cuda, feat_side, focal_length,
                thread_count,
                lambda m: print(m, flush=True), cli_progress, cancel,
            )
        finally:
            print()
        return

    print(f"Unknown sub-command: {sub}")
    sys.exit(2)
