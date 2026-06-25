# DJI Frame Extractor — GPS EXIF + Similarity

A cross-platform **PySide6** GUI (with a headless CLI) that extracts JPEG
frames from DJI drone videos, embeds per-frame GPS coordinates from the
matching `.SRT` sidecar into EXIF, and writes a single sequentially-numbered
folder (`<folder>_1.jpg`, `<folder>_2.jpg`, …) — ready to feed into COLMAP,
3D Gaussian Splatting, or photogrammetry pipelines.

Two extraction modes:

- **Fixed interval** — every Nth frame via an ffmpeg pipeline (optional GPU
  decode hwaccel).
- **Adaptive (similarity)** — decode every frame and keep one whenever the
  estimated geometric overlap with the last-kept frame drops into a target
  band (e.g. 70 % ± 5 %). Solves the "drone flies fast vs. slow" problem.
  Detectors: **ORB** (fast, optional `cv2.cuda` GPU) or **SIFT** (robust, CPU).

Plus optional **center crop** and **NxN grid split** per frame (focal length
auto-rescaled for the reduced field of view).

Supports **Windows / macOS / Linux**. CPU executables for all three are built
by [GitHub Actions](.github/workflows/release.yml) on each tagged release; a
GPU-accelerated **Windows CUDA** build is produced locally (see below).

---

## Versions

### v1.0.0 — PySide6 rewrite, modular refactor, CUDA build + CI

- **New PySide6 desktop UI** replacing the old Tkinter window: a modern
  themed layout with mode "cards", grouped option panels, live GPU/CUDA
  status chips, drag-and-drop input folder, progress bar and a dark log pane.
- **Modular refactor** of the former single 1800-line file into packages:
  `src/core/` (extraction engine), `src/cli.py` (headless CLI), `src/gui/`
  (PySide6 UI), reusing the existing `features/` and `src/shared/` helpers.
  Extraction behaviour is unchanged.
- **Local Windows CUDA build** (`cuda_build/`): bundles a CUDA-enabled OpenCV
  so the adaptive ORB path runs on the GPU (`cv2.cuda_ORB`) and ships an
  NVDEC-capable ffmpeg — produced locally because CUDA OpenCV isn't available
  on CI runners.
- **Multi-platform CI** (`.github/workflows/release.yml`): PyInstaller builds
  CPU executables for Windows / macOS / Linux and attaches them to the
  GitHub Release on each `v*` tag.

Carried over from the original tool: fixed-interval + adaptive extraction,
ORB/SIFT overlap estimation (RANSAC homography → corner warp → convex
intersection), per-frame GPS EXIF via `piexif`, center crop, 2x2 / 3x3 grid
split, focal-length rescale, multi-video sequential numbering, and the
optional decode hwaccel.

---

## Quick start

### Pre-built binaries (no Python required)

Download from the latest [Release](../../releases/latest):

- **Windows (x64, CPU)** — `extract-frames-windows-x64.zip`. Extract, run
  `extract-frames.exe`. ffmpeg / ffprobe bundled.
- **Windows (x64, CUDA)** — `extract-frames-windows-cuda-x64.zip`. Same, but
  the adaptive ORB detector and ffmpeg decode use your NVIDIA GPU. Requires a
  recent NVIDIA driver.
- **macOS (Apple Silicon)** — `extract-frames-macos-arm64`
  (`chmod +x … && ./…`). `brew install ffmpeg` on the host.
- **Linux (x86_64)** — `extract-frames-linux-x86_64`
  (`chmod +x … && ./…`). `apt install ffmpeg`.

Unsigned binaries: on Windows SmartScreen → **More info → Run anyway**; on
macOS Gatekeeper → `xattr -d com.apple.quarantine <file>`.

### Run from source

```bash
pip install -r requirements.txt    # PySide6, opencv-python, numpy, piexif
# plus ffmpeg/ffprobe on PATH (brew/apt install ffmpeg, or ffmpeg.org on Windows)

python extract_frames_with_gps_similarity.py          # GUI
```

### CLI

```bash
# Fixed interval (every 30th frame, scaled to 1080p, q=2, GPU decode)
python extract_frames_with_gps_similarity.py --cli fixed \
    /path/to/videos /path/to/out 30 1920x1080 2 --gpu

# Adaptive (target overlap 70%, ±5%, ORB, optional cv2.cuda)
python extract_frames_with_gps_similarity.py --cli adaptive \
    /path/to/videos /path/to/out 70 5 ORB 1920x1080 2 --cv2-cuda

# Optional flags for both: --crop WxH  --grid 2x2|3x3  --focal MM  --threads N
```

---

## Building

### CPU executables (CI, all platforms)

Push a `v*` tag; `.github/workflows/release.yml` builds Win/Mac/Linux with
PyInstaller and publishes them on the Release. To build the CPU Windows
exe locally:

```bash
pip install pyinstaller PySide6 opencv-python numpy piexif
cd cross_build
python fetch_or_provide ffmpeg.exe + ffprobe.exe into bin/   # see workflow
python -m PyInstaller build.spec --clean --noconfirm
```

### Windows CUDA executable (local only)

CUDA OpenCV is not on PyPI and CI runners have no GPU, so this build is local.
It uses the Python interpreter that already has a **CUDA-enabled** `cv2`
(verify with `python -c "import cv2; print(cv2.cuda.getCudaEnabledDeviceCount())"`
→ must be ≥ 1):

```bat
cuda_build\build_cuda.bat
```

The script installs PyInstaller + PySide6 into that interpreter (it does **not**
touch the CUDA `cv2`), downloads an NVDEC-capable ffmpeg into `cuda_build\bin\`,
and produces `cuda_build\dist\extract-frames-windows-cuda-x64.zip`.

---

## How adaptive overlap works

For each frame (downsampled for speed) the estimator detects ORB/SIFT
features, KNN-matches against the last-kept frame with a Lowe ratio test,
solves a RANSAC homography, warps the frame corners through it, intersects
with the kept frame's rectangle (`cv2.intersectConvexConvex`), and reports the
intersection-area / frame-area ratio as overlap. A frame is kept when overlap
drops to ≤ target + tolerance, then the chain re-anchors on it — so hovering
skips frames and fast sweeps sample densely.

---

## Privacy note

`.SRT` sidecars contain precise GPS coordinates of every flight. `.gitignore`
excludes `*.MP4`, `*.SRT`, and `frames*/` so flight data is never pushed.

---

## Repository layout

```
.
├── extract_frames_with_gps_similarity.py  # thin entry (GUI / --cli dispatch)
├── src/
│   ├── core/        # extraction engine (SRT, probe, overlap, extract_*, exif, pipeline)
│   ├── gui/         # PySide6 UI (app.py, style.py)
│   ├── cli.py       # headless CLI
│   └── shared/      # geometry + focal-length helpers
├── features/        # center_crop, grid_split
├── cross_build/     # PyInstaller CPU build (CI)
├── cuda_build/      # PyInstaller Windows CUDA build (local)
├── .github/workflows/release.yml
└── docs/            # architecture.md, change_log.md
```
