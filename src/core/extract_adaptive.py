#!/usr/bin/env python3
"""Adaptive (similarity-based) extraction via the cv2 per-frame pipeline.

Decodes every frame, estimates geometric overlap with the last-kept frame
(OverlapEstimator), and keeps a frame whenever the overlap drops into the
target band. Center crop is applied before feature detection so the overlap
estimate sees exactly the pixels that are saved; grid split is applied at
save time. GPS EXIF is written afterwards from the SRT map.
"""

import os
import platform
import shutil
import threading
from pathlib import Path

from features.center_crop.center_crop import center_crop_frame, crop_label
from features.grid_split.grid_split import grid_label, split_frame
from src.shared.focal import effective_focal

from .exif import _write_gps_exif
from .imports import _try_import_cv2
from .overlap import OverlapEstimator


def extract_video_adaptive(
    video: Path, srt_path, gps_map, max_src,
    output_dir: Path, start_number: int,
    target_overlap: float, tolerance: float,
    detector_name: str, prefer_cv2_cuda: bool,
    feature_long_side: int,
    resolution, crop, grid_n, jpeg_quality: int,
    focal_length: float,
    name_prefix: str,
    base_progress: int, total_progress: int,
    log, set_progress, cancel_event: threading.Event,
):
    cv2, np, err = _try_import_cv2()
    if cv2 is None:
        raise RuntimeError(
            "Adaptive mode requires opencv-python.\n"
            "Install:  pip install opencv-python numpy\n"
            f"(import error: {err})"
        )

    log(f"  SRT: {srt_path.name if srt_path else 'MISSING'} "
        f"({len(gps_map)} GPS entries)")

    cap = cv2.VideoCapture(str(video))
    _tmp_link: Path | None = None
    if not cap.isOpened() and platform.system() == "Windows":
        # cv2.VideoCapture can't handle non-ASCII paths on Windows;
        # create a temp hardlink with an ASCII-safe name.
        import tempfile
        tmp_dir = Path(tempfile.gettempdir())
        _tmp_link = tmp_dir / f"_dji_extract_{os.getpid()}{video.suffix}"
        try:
            _tmp_link.unlink(missing_ok=True)
            os.link(str(video), str(_tmp_link))
        except OSError:
            try:
                shutil.copy2(str(video), str(_tmp_link))
            except OSError:
                _tmp_link = None
        if _tmp_link and _tmp_link.exists():
            cap = cv2.VideoCapture(str(_tmp_link))
    if not cap.isOpened():
        if _tmp_link:
            try:
                _tmp_link.unlink(missing_ok=True)
            except OSError:
                pass
        log("  Could not open video with cv2.VideoCapture; skipping.")
        return 0

    nframes_cv = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or max_src

    estimator = OverlapEstimator(
        detector=detector_name, prefer_cuda=prefer_cv2_cuda,
        downsample_long_side=feature_long_side,
    )

    # cv2 IMWRITE_JPEG_QUALITY uses 0..100 (higher is better).
    # ffmpeg -q:v uses 1..31 (lower is better). Convert linearly.
    cv2_q = max(1, min(100, int(round(100 - (jpeg_quality - 1) * 80 / 30))))

    upper = float(target_overlap) + float(tolerance)
    lower = float(target_overlap) - float(tolerance)
    upper = min(0.99, max(0.05, upper))
    lower = min(0.95, max(0.01, lower))

    res_label = f"{resolution[0]}x{resolution[1]}" if resolution else "original"
    log(f"  [Adaptive] target overlap={target_overlap*100:.0f}% "
        f"(+/-{tolerance*100:.0f}%), detector={estimator.description}, "
        f"feat side={feature_long_side}px, crop={crop_label(crop)}, "
        f"grid={grid_label(grid_n)}, res={res_label}, jpeg q={cv2_q}")

    written = 0
    src_indices_kept = []
    last_features = None
    last_kept_src = 0
    src_idx = 0
    last_overlap = 1.0
    src_dims = None  # (w, h) of the original frames, for focal rescale

    def _save(frame, dst_start):
        """Write the frame (or its grid tiles) starting at index
        dst_start; return the number of files written."""
        outs = split_frame(frame, grid_n) if grid_n else [frame]
        for k, img in enumerate(outs):
            if resolution is not None:
                img = cv2.resize(
                    img, (resolution[0], resolution[1]),
                    interpolation=cv2.INTER_LANCZOS4,
                )
            out_path = output_dir / f"{name_prefix}_{dst_start + k}.jpg"
            # cv2.imwrite silently fails on Windows with non-ASCII paths;
            # imencode + write_bytes works regardless of path encoding.
            ok, buf = cv2.imencode(".jpg", img,
                                   [cv2.IMWRITE_JPEG_QUALITY, cv2_q])
            if ok:
                out_path.write_bytes(buf.tobytes())
            else:
                log(f"    WARNING: failed to encode {out_path.name}")
        return len(outs)

    while True:
        if cancel_event.is_set():
            break
        ok, frame = cap.read()
        if not ok:
            break
        src_idx += 1

        if src_dims is None:
            src_dims = (frame.shape[1], frame.shape[0])

        if crop is not None:
            # Crop before feature detection so the overlap estimate is
            # computed on the same pixels that get saved.
            frame = center_crop_frame(frame, crop[0], crop[1])

        if last_features is None:
            # Always keep the first frame (no previous to compare to).
            dst_idx = start_number + written
            n_out = _save(frame, dst_idx)
            # Every tile of a frame shares that frame's GPS entry.
            src_indices_kept.extend([src_idx] * n_out)
            written += n_out
            last_kept_src = src_idx
            last_features = estimator.features(frame)
            log(f"    KEEP src #{src_idx} -> {name_prefix}_{dst_idx}.jpg"
                f"{f' (+{n_out - 1} tiles)' if n_out > 1 else ''} "
                f"(overlap=N/A, first frame)")
        else:
            fcur = estimator.features(frame)
            ov = estimator.overlap(last_features, fcur)
            keep = False
            reason = ""
            if ov <= 0.0:
                # Match failed entirely -> probably a big jump or texture
                # loss. Re-anchor on this frame.
                if src_idx - last_kept_src >= 1:
                    keep = True
                    reason = "match-fail re-anchor"
            elif ov <= upper:
                keep = True
                reason = f"<= upper {upper*100:.0f}%"
            # else: overlap still too high -> skip and keep walking.
            last_overlap = ov

            if keep:
                dst_idx = start_number + written
                n_out = _save(frame, dst_idx)
                src_indices_kept.extend([src_idx] * n_out)
                written += n_out
                gap = src_idx - last_kept_src
                last_kept_src = src_idx
                last_features = fcur
                log(f"    KEEP src #{src_idx} -> {name_prefix}_{dst_idx}.jpg"
                    f"{f' (+{n_out - 1} tiles)' if n_out > 1 else ''} "
                    f"(overlap={ov*100:.1f}%, gap={gap} frames, {reason})")

        # Progress: based on source-frame index walked, not output frames.
        set_progress(base_progress + src_idx, total_progress)

        if src_idx % 200 == 0:
            log(f"    ...walked src {src_idx}/{nframes_cv}, "
                f"kept {written}, last overlap={last_overlap*100:.1f}%")

    cap.release()
    if _tmp_link:
        try:
            _tmp_link.unlink(missing_ok=True)
        except OSError:
            pass

    if cancel_event.is_set():
        log("  Cancelled.")
        return 0

    log(f"  Wrote {written} JPEGs (kept src indices: "
        f"{src_indices_kept[0] if src_indices_kept else '-'}..."
        f"{src_indices_kept[-1] if src_indices_kept else '-'}).")
    set_progress(base_progress + nframes_cv, total_progress)

    # User-entered focal length describes the original frame; rescale
    # for the FOV reduction caused by crop / grid split.
    eff_focal = focal_length
    if src_dims is not None:
        eff_focal = effective_focal(
            focal_length, src_dims[0], src_dims[1], crop, grid_n)
        if abs(eff_focal - focal_length) > 1e-9:
            log(f"  Focal length: {focal_length:g} mm -> {eff_focal:.2f} mm "
                f"(FOV factor {eff_focal / focal_length:.2f} from crop/grid)")

    _write_gps_exif(output_dir, start_number, written, src_indices_kept,
                    gps_map, video.stem, log, focal_length=eff_focal,
                    name_prefix=name_prefix)
    return written
