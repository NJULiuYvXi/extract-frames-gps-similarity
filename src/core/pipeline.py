#!/usr/bin/env python3
"""Top-level extraction driver.

``process_all`` plans every MP4 in the input folder, runs the selected mode
(fixed / adaptive) either sequentially or across a thread pool (one video per
worker, written to temp dirs then merged into a single contiguous numbering),
and reports progress / log via the supplied callbacks. UI-agnostic.
"""

import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from features.grid_split.grid_split import grid_label

from .extract_adaptive import extract_video_adaptive
from .extract_fixed import extract_video_fixed, plan_video


def process_all(
    input_dir: Path,
    output_dir: Path,
    mode: str,                # "fixed" or "adaptive"
    interval: int,
    resolution,
    crop,                     # (w, h) center crop or None
    grid_n,                   # N for NxN grid split or None
    jpeg_quality: int,
    hwaccel,                  # for fixed mode
    target_overlap: float,    # for adaptive mode
    tolerance: float,
    detector_name: str,       # "ORB" or "SIFT"
    prefer_cv2_cuda: bool,
    feature_long_side: int,
    focal_length: float,
    thread_count: int,
    log,
    set_progress,
    cancel_event: threading.Event,
):
    videos = sorted(
        [p for p in input_dir.iterdir()
         if p.is_file() and p.suffix.lower() == ".mp4"
         and not p.name.startswith("._")],
        key=lambda p: p.name,
    )
    if not videos:
        log(f"No MP4 files found in {input_dir}")
        return

    # Derive output filename prefix from the input folder name.
    name_prefix = input_dir.name or "frame"
    log(f"Output filename prefix: {name_prefix}_<n>.jpg")

    log(f"Mode: {mode}")
    if crop is not None:
        log(f"Center crop: {crop[0]}x{crop[1]} "
            "(true crop, applied before any output scaling)")
    if grid_n:
        log(f"Grid split: {grid_label(grid_n)} per frame "
            "(applied after crop; all tiles share the frame's GPS; "
            "focal length rescaled for the reduced FOV)")
    if mode == "fixed":
        if hwaccel:
            log(f"GPU decode: ON -> {hwaccel['name']} ({hwaccel['description']})")
        else:
            log("GPU decode: OFF (CPU)")
    else:
        log(f"Detector: {detector_name}, "
            f"target overlap={target_overlap*100:.0f}% "
            f"(+/-{tolerance*100:.0f}%), "
            f"prefer cv2.cuda={prefer_cv2_cuda}")

    log(f"Found {len(videos)} video(s). Planning...")

    tiles_per_frame = grid_n * grid_n if grid_n else 1

    plans = []
    total_units = 0  # progress unit = source frame walked
    for v in videos:
        srt_path, gps_map, max_src, _n_expected = plan_video(v, interval)
        plans.append((v, srt_path, gps_map, max_src))
        # In fixed mode, ffmpeg's frame= counter goes up to ~ n_expected
        # output frames (tiles, when grid split is on). In adaptive mode,
        # we walk every src frame.
        if mode == "fixed":
            n_expected = (max_src + interval - 1) // interval if max_src > 0 else 0
            total_units += n_expected * tiles_per_frame
        else:
            total_units += max_src
        log(f"  - {v.name}: {max_src} src frames "
            f"(SRT: {'yes' if srt_path else 'MISSING'})")
    log(f"Total progress units: {total_units}")
    log("")

    if total_units == 0:
        log("Nothing to extract.")
        return

    set_progress(0, total_units)
    output_dir.mkdir(parents=True, exist_ok=True)

    effective_threads = max(1, min(int(thread_count), len(plans)))
    log(f"Worker threads: {effective_threads}")
    log("")

    if effective_threads == 1:
        # ---- Sequential path (zero behaviour change apart from prefix) -----
        counter = 1
        base = 0
        total_written = 0
        for i, (video, srt_path, gps_map, max_src) in enumerate(plans):
            if cancel_event.is_set():
                log("Cancelled.")
                break
            log(f"[{i + 1}/{len(plans)}] {video.name}")
            if mode == "fixed":
                written = extract_video_fixed(
                    video, srt_path, gps_map, max_src,
                    output_dir, counter, interval, resolution, crop, grid_n,
                    jpeg_quality,
                    hwaccel, focal_length, name_prefix,
                    base, total_units,
                    log, set_progress, cancel_event,
                )
                base += (((max_src + interval - 1) // interval)
                         * tiles_per_frame if max_src > 0 else 0)
            else:
                written = extract_video_adaptive(
                    video, srt_path, gps_map, max_src,
                    output_dir, counter,
                    target_overlap, tolerance,
                    detector_name, prefer_cv2_cuda, feature_long_side,
                    resolution, crop, grid_n, jpeg_quality, focal_length,
                    name_prefix,
                    base, total_units,
                    log, set_progress, cancel_event,
                )
                base += max_src
            counter += written
            total_written += written
            set_progress(base, total_units)

        log("")
        log(f"=== Done. Extracted {total_written} frames into {output_dir} ===")
        return

    # ---- Parallel path: per-video temp subdirs + post-renumber -----------
    tmp_dirs: list[Path] = []
    for i in range(len(plans)):
        td = output_dir / f"_tmp_v{i}"
        # Clean any stale temp dir from a previous run.
        if td.exists():
            shutil.rmtree(td, ignore_errors=True)
        td.mkdir(parents=True, exist_ok=True)
        tmp_dirs.append(td)

    # Shared progress accumulator -- each thread reports deltas.
    progress_lock = threading.Lock()
    shared_progress = [0]

    def make_thread_progress():
        last = [0]
        def _progress(current: int, _total: int):
            delta = current - last[0]
            last[0] = current
            if delta == 0:
                return
            with progress_lock:
                shared_progress[0] += delta
                cur = shared_progress[0]
            set_progress(cur, total_units)
        return _progress

    def _extract_one(idx: int, video: Path, srt_path, gps_map, max_src,
                     tmp_dir: Path):
        if cancel_event.is_set():
            return idx, 0
        log(f"[thread] start [{idx + 1}/{len(plans)}] {video.name}")
        thread_progress = make_thread_progress()
        try:
            if mode == "fixed":
                w = extract_video_fixed(
                    video, srt_path, gps_map, max_src,
                    tmp_dir, 1, interval, resolution, crop, grid_n,
                    jpeg_quality,
                    hwaccel, focal_length, name_prefix,
                    0, total_units,
                    log, thread_progress, cancel_event,
                )
            else:
                w = extract_video_adaptive(
                    video, srt_path, gps_map, max_src,
                    tmp_dir, 1,
                    target_overlap, tolerance,
                    detector_name, prefer_cv2_cuda, feature_long_side,
                    resolution, crop, grid_n, jpeg_quality, focal_length,
                    name_prefix,
                    0, total_units,
                    log, thread_progress, cancel_event,
                )
        except Exception as e:  # noqa: BLE001
            log(f"[thread] ERROR on {video.name}: {e}")
            return idx, 0
        log(f"[thread] done  [{idx + 1}/{len(plans)}] {video.name}: {w} frames")
        return idx, w

    results: list[tuple[int, int]] = []
    with ThreadPoolExecutor(max_workers=effective_threads) as pool:
        futures = [
            pool.submit(_extract_one, i, v, s, g, m, tmp_dirs[i])
            for i, (v, s, g, m) in enumerate(plans)
        ]
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:  # noqa: BLE001
                log(f"[thread] future exception: {e}")

    if cancel_event.is_set():
        log("Cancelled. Cleaning up temp dirs...")
        for td in tmp_dirs:
            shutil.rmtree(td, ignore_errors=True)
        return

    # ---- Phase 3: merge + renumber, in video order ---------------------
    log("")
    log("Merging extracted frames into final sequential numbering...")
    results.sort(key=lambda r: r[0])
    counter = 1
    total_written = 0
    for idx, written in results:
        td = tmp_dirs[idx]
        for j in range(1, written + 1):
            if cancel_event.is_set():
                break
            src = td / f"{name_prefix}_{j}.jpg"
            dst = output_dir / f"{name_prefix}_{counter}.jpg"
            if not src.exists():
                continue
            try:
                if dst.exists():
                    dst.unlink()
                src.rename(dst)
            except OSError as e:
                log(f"  rename failed {src.name} -> {dst.name}: {e}")
                continue
            counter += 1
            total_written += 1
        shutil.rmtree(td, ignore_errors=True)

    log("")
    log(f"=== Done. Extracted {total_written} frames into {output_dir} ===")
