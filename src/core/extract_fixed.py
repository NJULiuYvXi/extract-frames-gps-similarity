#!/usr/bin/env python3
"""Fixed-interval extraction via the ffmpeg pipeline (decode hwaccel applies).

Every Nth frame is selected by ffmpeg; the optional center crop, grid split
and output scale are applied as -vf filters before JPEG encoding. GPS EXIF
is written afterwards from the SRT map.
"""

import subprocess
import threading
from pathlib import Path

from features.center_crop.center_crop import (
    crop_label,
    ffmpeg_center_crop_filter,
)
from features.grid_split.grid_split import (
    ffmpeg_grid_filters,
    grid_label,
)
from src.shared.focal import effective_focal

from .exif import _write_gps_exif
from .probe import probe_frame_count, probe_video_dims
from .srt import find_srt, parse_srt


def plan_video(video: Path, interval: int):
    srt_path = find_srt(video)
    gps_map = parse_srt(srt_path) if srt_path else {}
    max_src = max(gps_map) if gps_map else probe_frame_count(video)
    n_expected = 0
    if max_src > 0 and interval > 0:
        n_expected = (max_src + interval - 1) // interval
    return srt_path, gps_map, max_src, n_expected


def extract_video_fixed(
    video: Path, srt_path, gps_map, max_src,
    output_dir: Path, start_number: int,
    interval: int, resolution, crop, grid_n, jpeg_quality: int,
    hwaccel, focal_length: float,
    name_prefix: str,
    base_progress: int, total_progress: int,
    log, set_progress, cancel_event: threading.Event,
):
    log(f"  SRT: {srt_path.name if srt_path else 'MISSING'} "
        f"({len(gps_map)} GPS entries)")
    if max_src <= 0:
        log("  Could not determine frame count; skipping.")
        return 0

    selected_src = list(range(1, max_src + 1, interval))
    if not selected_src:
        return 0

    vf_parts = []
    if interval > 1:
        vf_parts.append(f"select='not(mod(n\\,{interval}))'")
    if crop is not None:
        # Crop first so grid split / scale operate on the cropped image.
        vf_parts.append(ffmpeg_center_crop_filter(crop[0], crop[1]))
    if grid_n:
        # untile turns each frame into n*n sequential tiles (row-major),
        # so image2 numbers the tiles consecutively.
        vf_parts.extend(ffmpeg_grid_filters(grid_n))
    if resolution is not None:
        vf_parts.append(f"scale={resolution[0]}:{resolution[1]}:flags=lanczos")

    tiles = grid_n * grid_n if grid_n else 1
    expected_outputs = len(selected_src) * tiles

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y"]
    if hwaccel:
        cmd += hwaccel["args"]
    cmd += ["-i", str(video)]
    if vf_parts:
        cmd += ["-vf", ",".join(vf_parts)]
    if interval > 1:
        cmd += ["-fps_mode", "vfr"]
    cmd += [
        "-q:v", str(jpeg_quality),
        "-start_number", str(start_number),
        "-progress", "pipe:1", "-nostats",
        str(output_dir / f"{name_prefix}_%d.jpg"),
    ]

    res_label = f"{resolution[0]}x{resolution[1]}" if resolution else "original"
    hw_label = hwaccel["name"] if hwaccel else "cpu"
    log(f"  [Fixed] Extracting ~{expected_outputs} files "
        f"(crop: {crop_label(crop)}, grid: {grid_label(grid_n)}, "
        f"res: {res_label}, q={jpeg_quality}, decode: {hw_label})...")

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )

    def pump_stderr():
        assert proc.stderr is not None
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                log(f"    ffmpeg: {line}")

    t_err = threading.Thread(target=pump_stderr, daemon=True)
    t_err.start()

    last_n = 0
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("frame="):
                try:
                    last_n = int(line.split("=", 1)[1])
                except ValueError:
                    pass
                set_progress(base_progress + last_n, total_progress)
            if cancel_event.is_set():
                proc.terminate()
                break
    finally:
        proc.wait()
        t_err.join(timeout=1.0)

    if cancel_event.is_set():
        return 0

    if proc.returncode != 0:
        hint = ""
        if hwaccel:
            hint = (f"  (Hint: '{hwaccel['name']}' decode failed; "
                    "turn GPU off and retry.)")
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode}{hint}")

    written = 0
    for i in range(expected_outputs):
        if (output_dir / f"{name_prefix}_{start_number + i}.jpg").exists():
            written = i + 1
        else:
            break

    log(f"  Wrote {written} JPEGs.")
    set_progress(base_progress + written, total_progress)

    # Every tile of a frame shares that frame's GPS entry.
    exif_src = (selected_src if tiles == 1
                else [s for s in selected_src for _ in range(tiles)])

    # User-entered focal length describes the original frame; rescale
    # for the FOV reduction caused by crop / grid split.
    eff_focal = focal_length
    src_dims = probe_video_dims(video)
    if src_dims is not None:
        eff_focal = effective_focal(
            focal_length, src_dims[0], src_dims[1], crop, grid_n)
    elif grid_n and crop is None:
        eff_focal = focal_length * grid_n
    elif crop is not None:
        log("  WARNING: could not probe source dimensions; focal length "
            "NOT adjusted for crop.")
    if abs(eff_focal - focal_length) > 1e-9:
        log(f"  Focal length: {focal_length:g} mm -> {eff_focal:.2f} mm "
            f"(FOV factor {eff_focal / focal_length:.2f} from crop/grid)")

    _write_gps_exif(output_dir, start_number, written, exif_src, gps_map,
                    video.stem, log, focal_length=eff_focal,
                    name_prefix=name_prefix)
    return written
