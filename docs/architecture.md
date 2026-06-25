# Architecture

Last updated: 2026-06-25

## Overview

DJI drone video -> sequential JPEG frames with GPS EXIF metadata, aimed at
3D reconstruction workflows (Gaussian splatting / photogrammetry / COLMAP).
A **PySide6** desktop GUI plus a headless `--cli` mode share one UI-agnostic
extraction engine.

As of v1.0.0 the former single ~1800-line module was split into packages
(`src/core`, `src/gui`, `src/cli`) and the GUI was rewritten from Tkinter to
PySide6. Extraction behaviour is unchanged; the engine still exposes the same
`process_all(...)` driver taking `log` / `set_progress` callbacks and a
`threading.Event` cancel.

## Module structure

```
extract_frames_with_gps_similarity/
├── extract_frames_with_gps_similarity.py   # THIN entry: main() -> CLI or GUI
├── src/
│   ├── core/                       # UI-agnostic extraction engine
│   │   ├── imports.py              # _try_import_cv2 / _try_import_piexif (lazy)
│   │   ├── srt.py                  # parse_srt, find_srt (DJI .SRT -> GPS map)
│   │   ├── probe.py                # probe_frame_count/video_dims, parse_resolution,
│   │   │                           #   probe_hwaccel, probe_cv2_cuda
│   │   ├── overlap.py              # OverlapEstimator (ORB/SIFT + RANSAC homography)
│   │   ├── exif.py                 # _write_gps_exif (piexif camera + GPS + focal)
│   │   ├── extract_fixed.py        # plan_video, extract_video_fixed (ffmpeg)
│   │   ├── extract_adaptive.py     # extract_video_adaptive (cv2 per-frame walk)
│   │   └── pipeline.py             # process_all (plan, sequential/parallel, merge)
│   ├── gui/
│   │   ├── app.py                  # MainWindow + ExtractWorker(QThread) + run()
│   │   └── style.py                # STYLESHEET (modern Qt theme)
│   ├── cli.py                      # headless --cli parser/dispatch
│   └── shared/
│       ├── geometry.py             # crop/tile output dims (single source of truth)
│       └── focal.py                # focal length rescale after crop/grid
├── features/
│   ├── center_crop/center_crop.py  # center-crop feature
│   └── grid_split/grid_split.py    # NxN grid-split feature
├── cross_build/                    # PyInstaller CPU build (CI)
│   ├── build.spec, main_packaged.py, windows_version.txt
├── cuda_build/                     # PyInstaller Windows CUDA build (local)
│   ├── build_cuda.spec, build_cuda.bat, fetch_ffmpeg_cuda.ps1,
│   │   main_packaged.py, windows_version.txt
├── .github/workflows/release.yml   # CPU Win/Mac/Linux build -> Release on v* tag
└── docs/architecture.md, change_log.md
```

## Dependency direction

```
extract_frames_with_gps_similarity.py (entry)
        ├── src.cli ─────────────┐
        └── src.gui.app ─────────┤
                                 ▼
                        src.core.pipeline
                     ┌───────────┴────────────┐
              src.core.extract_fixed   src.core.extract_adaptive
                     │                        │
        srt / probe / exif            overlap / exif / imports
                     └──────────┬─────────────┘
                       features.* + src.shared.*   (leaf helpers)
```

`features/*` and `src/shared/*` are leaves (features -> shared is the only
allowed direction). `src/core/*` import features + shared; `src/gui` and
`src/cli` import `src/core`. The entry module imports gui/cli lazily so the
GUI never loads unless launched.

## Features

### center_crop (features/center_crop/)

True center crop of each frame (discards pixels outside the WxH window; not
downsampling). `ffmpeg_center_crop_filter(w,h)` for the fixed (ffmpeg)
pipeline; `center_crop_frame(frame,w,h)` for the adaptive (cv2) pipeline.
Applied before any output scaling. EXIF focal length is rescaled for the
reduced FOV (src/shared/focal.py).

### grid_split (features/grid_split/)

Splits each (optionally cropped) frame into an NxN grid (2x2 / 3x3) of equal,
even-sized tiles, row-major. `ffmpeg_grid_filters(n)` (`crop` + `untile`, needs
ffmpeg >= 4.4) for fixed mode; `split_frame(frame,n)` for adaptive mode. All
tiles share the source frame's GPS; focal length rescaled per tile FOV. Order
of operations: center crop -> grid split -> output scaling.

## Shared utilities (src/shared/)

- `geometry.py` — `cropped_dims()`, `grid_tile_dims()`: single source of truth
  for output pixel dimensions after crop/grid, so the ffmpeg path, the cv2 path
  and the focal computation never disagree.
- `focal.py` — `effective_focal()`: rescales the user focal (which describes the
  original frame) by `factor = max(src dims) / max(final tile dims)`, matching
  COLMAP's `f_px = FocalLengthIn35mm / 35 * max(w, h)`. Output scaling is
  excluded (it doesn't change FOV).

## Dependencies

| Dependency              | Needed for                                              | Required?     |
| ----------------------- | ------------------------------------------------------- | ------------- |
| ffmpeg / ffprobe (PATH) | fixed-mode decode/extract, probing; untile needs >= 4.4 | yes           |
| piexif                  | EXIF (camera + GPS + focal)                             | yes           |
| opencv-python + numpy   | adaptive mode; CUDA build uses a local CUDA cv2          | adaptive only |
| PySide6                 | desktop GUI                                             | GUI only      |

## Data flow

```
input folder (MP4 + SRT)
  └─ pipeline.process_all: plan per video (SRT GPS map, frame count)
       ├─ fixed:    ffmpeg [-hwaccel] -vf select,(crop),(untile),(scale) -> JPEGs
       └─ adaptive: cv2 read -> (center crop) -> features/overlap -> keep?
                    -> (split into N*N tiles) -> (scale) -> imencode JPEG
  └─ exif._write_gps_exif: piexif camera tags + per-frame GPS from SRT map
       (each tile repeats its frame's GPS; focal rescaled for crop/grid FOV)
  └─ parallel runs (thread_count > 1) write to _tmp_v<i>/ then merge + renumber
```

Per-frame pixel order in both modes: decode -> center crop -> grid split ->
scale -> JPEG encode. GPS is unaffected by crop/grid/scale; focal is rescaled
when crop/grid reduce the FOV.

## Builds

- **CPU (all platforms, CI):** `.github/workflows/release.yml` runs PyInstaller
  against `cross_build/build.spec` on Windows/macOS/Linux and attaches the
  binaries to the GitHub Release on each `v*` tag. Uses the PyPI (CPU)
  opencv-python wheel.
- **Windows CUDA (local):** `cuda_build/build_cuda.bat` runs PyInstaller under a
  Python whose `cv2` is CUDA-enabled, bundling that cv2 (+ its CUDA DLL deps,
  resolved from the CUDA toolkit bin on PATH), PySide6 and an NVDEC ffmpeg into
  `extract-frames-windows-cuda-x64.zip`. Not built on CI (no GPU / no PyPI CUDA
  wheel). The adaptive ORB path then runs on the GPU via `cv2.cuda_ORB`.
```
