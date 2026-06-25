# Change Log

### 2026-06-25 - v1.0.0: PySide6 rewrite, modular refactor, CUDA build + CI

Files (new): src/core/{__init__,imports,srt,probe,overlap,exif,extract_fixed,
extract_adaptive,pipeline}.py; src/cli.py; src/gui/{__init__,app,style}.py;
requirements.txt; README.md; .gitignore; cross_build/{build.spec,
main_packaged.py,windows_version.txt}; cuda_build/{build_cuda.spec,
build_cuda.bat,fetch_ffmpeg_cuda.ps1,main_packaged.py,windows_version.txt};
.github/workflows/release.yml
Files (rewritten): extract_frames_with_gps_similarity.py (1844 -> ~50 lines,
thin entry); docs/architecture.md
Change:

- **Modular refactor.** Split the single ~1800-line module into packages with
  no behaviour change. The extraction engine moved verbatim into `src/core/`
  (srt, probe, overlap, exif, extract_fixed, extract_adaptive, pipeline); the
  `--cli` block into `src/cli.py`; the entry file is now a thin `main()` that
  dispatches `--cli` -> CLI else launches the GUI. Internal imports rewired
  (core -> features + src.shared; gui/cli -> core). cv2/numpy/piexif stay lazily
  imported so the GUI starts and fixed mode works without opencv installed.
  Why: the monolith was unmaintainable; CLAUDE.md rule 1 (shared in /src,
  features in /features).

- **PySide6 GUI** (`src/gui/app.py` + `style.py`) replaces the Tkinter `App`.
  Modern themed layout: folder cards with drag-and-drop, mode "cards" driving a
  QStackedWidget, grouped option panels, live GPU/cv2.cuda status chips with
  Re-detect, progress bar + status, dark monospace log. Extraction runs in an
  `ExtractWorker(QThread)` that calls the unchanged `process_all` and relays
  log/progress via Qt signals (queued to the GUI thread); cancel uses the same
  `threading.Event`. All prior validation/guards preserved.

- **cv2.cuda bug fix** (`src/core/overlap.py`): the GPU ORB path guarded empty
  descriptors with `GpuMat.size().width`, which raises `AttributeError` on
  OpenCV >= 4.x where `GpuMat.size()` returns a `(w, h)` tuple — so the GPU
  adaptive path crashed after the first frame. Switched to `GpuMat.empty()`.
  Why: makes the whole point of the CUDA build (GPU ORB) actually work.

- **Local Windows CUDA build** (`cuda_build/`). `build_cuda.bat` runs PyInstaller
  under the Python whose `cv2` is CUDA-enabled (default `py -3.10`), bundling
  that cv2 (its CUDA DLL deps — cublas/cufft/npp/cudart + opencv_cuda* — are
  pulled in by PyInstaller's dependency scan from the CUDA toolkit bin on PATH),
  PySide6, and an NVDEC ffmpeg (`fetch_ffmpeg_cuda.ps1`, BtbN win64-gpl) into
  `extract-frames-windows-cuda-x64.zip`. Pip install is `pyinstaller PySide6`
  only (no `--upgrade`, no opencv-python) so the CPU PyPI wheel never shadows
  the CUDA cv2. Why: CUDA OpenCV isn't on PyPI and CI has no GPU, so CUDA is
  built locally (global rule "如果需要cuda，则在本地编译").

- **Multi-platform CI** (`.github/workflows/release.yml`, `cross_build/`). On a
  `v*` tag, PyInstaller builds CPU executables for Windows (onedir zip) / macOS
  arm64 / Linux x86_64 and attaches them to the GitHub Release. Deps now include
  PySide6; the spec collects `src`/`features` submodules + PySide6. CI artifacts
  are CPU-only by design.

Verification:

- py_compile + import of the whole tree on Python 3.11 (no cv2) and 3.10 (CUDA
  cv2): OK; lazy-import design confirmed.
- Synthetic 1920x1080 clip + DJI-format SRT: `--cli fixed` interval 10 +
  `--crop 1280x720` -> 6 JPEGs at 1280x720, EXIF GPS 6/6, focal 24 -> 36 mm. OK.
- `--cli adaptive` on a panning clip: CPU ORB kept 11 frames, cv2.cuda ORB kept
  14 (overlaps walking the target band) after the size()/empty() fix. OK.
- GUI: rendered both mode views (screenshots); cv2.cuda chip shows green
  "available (1 device(s))"; drove the real QThread worker end-to-end (fixed,
  interval 20 -> 3 JPEGs, status "Done."). OK.
- CUDA build: `extract-frames-windows-cuda-x64.zip` produced with opencv_cuda* +
  CUDA runtime DLLs + NVDEC ffmpeg bundled.

### 2026-06-11 - Add grid-split feature (2x2 / 3x3 tiles) + focal length rescale for crop & grid

File: features/grid_split/grid_split.py
Lines: 1-105 (new file)
Change:

- New feature: splits each (optionally center-cropped) frame into an
  NxN grid of equal tiles (presets 2x2 = 4 tiles, 3x3 = 9 tiles; e.g. a
  4K frame -> four 1080p images). Any aspect ratio supported.
- Tiles are emitted row-major; dimensions are trimmed symmetrically to
  a multiple of 2N so tiles are even-sized -- ffmpeg's untile cannot
  split 4:2:0 chroma at odd boundaries, and the cv2 path mirrors the
  rule so both pipelines produce identical tiles.
- `ffmpeg_grid_filters(n)` (crop-to-divisible + `untile=NxN`, ffmpeg >=
  4.4), `split_frame(frame, n)`, `parse_grid()`, `GRID_PRESETS`,
  `grid_label()`.
- Why: tiling lets 3D-reconstruction pipelines work on full-detail
  sub-images instead of one large frame.

File: src/shared/geometry.py
Lines: 1-33 (new file)
Change:

- `cropped_dims()` / `grid_tile_dims()`: single source of truth for the
  pixel dimensions produced by crop + grid, shared by the grid feature
  and the focal computation (CLAUDE.md rule 1: shared utilities in
  /src/shared).

File: src/shared/focal.py
Lines: 1-46 (new file)
Change:

- `effective_focal(focal_mm, src_w, src_h, crop, grid_n)`: rescales the
  user-entered focal length (which always describes the ORIGINAL frame)
  for the field of view kept after center crop and/or grid split:
  factor = max(src dims) / max(final tile dims). This matches COLMAP's
  EXIF convention f_px = FocalLengthIn35mm / 35 \* max(w, h), so f_px
  stays correct on cropped/tiled images. Examples: 2x2 -> x2, 3x3 ->
  x3, 1280x720 crop of 1920x1080 -> x1.5.
- Output scaling (resolution option) does not change FOV and is
  deliberately excluded from the factor.
- Why: without the rescale, reconstruction tools would derive a wrong
  focal prior from cropped/tiled images.

File: extract_frames_with_gps_similarity.py
Lines: docstring 41-49; imports 63-71; probe_video_dims 152-168 (new);
fixed mode 506-516, 530-538, 590-625; adaptive mode 654, 700-735,
764-795, 836-861; \_write_gps_exif 925 (FocalLengthIn35mmFilm now
rounds instead of truncating); process_all 999-1002, 1020-1025,
1031-1046, 1060-1106; GUI 1209, 1338-1352, 1571, 1620-1624,
1672-1681; CLI 1745-1754, 1764-1770, 1797-1800, 1816-1819
Change:

- Registered the grid-split feature entry points; tile logic itself
  lives in features/grid_split, focal/geometry in src/shared.
- Fixed mode: `untile` inserted into -vf after the center crop, before
  scale; expected-output accounting, ffmpeg progress units and the
  written-files check are tile-aware; source dims probed via new
  `probe_video_dims()` for the focal rescale.
- Adaptive mode: kept frames are split via `split_frame()` at save time
  (overlap estimation still runs on the whole cropped frame); source
  dims captured from the first decoded frame for the focal rescale.
- GPS: every tile of a frame reuses that frame's SRT entry (the source
  index list passed to \_write_gps_exif is repeated N\*N times per frame).
- EXIF focal: both modes now write `effective_focal(...)` instead of the
  raw user value whenever crop and/or grid reduce the FOV (crop-only
  runs are rescaled too, per the feature requirement); the adjustment
  is logged ("24 mm -> 48.00 mm (FOV factor 2.00)").
- GUI: "Grid split" combobox (Off / 2x2 / 3x3) under the Center crop
  row; rows below renumbered.
- CLI: new `--grid NxN` flag for both subcommands; usage text updated.

Verification:

- py_compile on all changed files: OK.
- Unit tests: parse_grid, geometry (incl. even-tile trim), split_frame
  row-major slicing, effective_focal (grid 2x2/3x3, crop-only, crop+
  grid, oversize clamp, portrait crop, odd dims): OK.
- End-to-end with synthetic 1920x1080 clip + generated DJI-format SRT:
  - fixed 2x2: 16 tiles @ 960x540, EXIF focal 24 -> 48 mm, each group
    of 4 tiles shares its frame's GPS, groups differ. OK.
  - fixed 3x3: 36 tiles @ 640x360, focal 72 mm, GPS groups of 9. OK.
  - fixed crop-only 1280x720: focal 24 -> 36 mm. OK.
  - adaptive crop 1280x720 + 2x2: 640x360 tiles, focal 72 mm. OK.
  - odd dims (crop 1279x719 + 2x2): both pipelines emit identical
    638x358 tiles, focal 72.23 mm (initial untile failure on odd
    chroma boundaries fixed by the 2N trim rule). OK.
- GUI smoke test (widget construction, preset parsing): OK.

### 2026-06-11 - Add center-crop feature (crop frame center to a specified resolution)

File: features/center_crop/center_crop.py
Lines: 1-77 (new file)
Change:

- New feature module: crops the central WxH window out of each frame.
  True crop (discards pixels outside the window), NOT downsampling.
- `ffmpeg_center_crop_filter(w, h)` builds a centered `crop=` -vf element
  for the ffmpeg (fixed-interval) pipeline; `min(iw,w)`/`min(ih,h)` guards
  clamp the crop to the source size so ffmpeg never errors on oversized
  crop requests.
- `center_crop_frame(frame, w, h)` slices the central region out of a
  numpy frame (cv2 / adaptive pipeline), clamped to the frame bounds.
- `CROP_PRESETS` and `crop_label()` for the GUI and run logs.
- Why: users need full-detail center extracts (e.g. for 3D reconstruction
  of the flight-path center) without the resolution loss of scaling.

File: features/**init**.py, features/center_crop/**init**.py
Lines: 1 (new files)
Change:

- Package markers for the new /features tree (CLAUDE.md rule 1).

File: extract_frames_with_gps_similarity.py
Lines: 56-62 (import), 36-40 (docstring), 462-481 / 502-507 (fixed mode),
569-576 / 637-641 / 672-675 (adaptive mode), 875-905 / 947-1031
(process_all + call sites), 1115-1118 / 1141-1144 / 1265-1289 /
1352-1359 / 1447-1461 / 1500-1510 / 1556-1577 (GUI),
1627-1635 / 1648-1653 / 1664-1683 (CLI)
Change:

- Registered the center-crop feature entry points (CLAUDE.md workflow
  step 3); all crop logic itself lives in features/center_crop/.
- Fixed mode: inserts the crop filter into the ffmpeg -vf chain BEFORE
  the optional scale filter, so scaling operates on the cropped image.
- Adaptive mode: crops each frame immediately after decode, so feature
  detection / overlap estimation run on exactly the pixels that get
  saved (cropping reduces field of view, which changes real overlap).
- `process_all`, `extract_video_fixed`, `extract_video_adaptive`, GUI
  worker and both CLI subcommands gained a `crop` parameter ((w, h) or
  None) threaded through sequential and parallel paths.
- GUI: new "Center crop (WxH)" row in Output options (preset combobox
  Off/4K/1440p/1080p/720p/Custom + custom WxH entry, mirroring the
  existing resolution row); rows below it renumbered.
- CLI: new `--crop WxH` flag for both `fixed` and `adaptive` subcommands;
  usage text updated.
- Why: feature registration as required by the new feature workflow.

Verification:

- `python -m py_compile` on both files: OK.
- Unit checks on filter string, centered slicing, clamping: OK.
- ffmpeg accepts the generated filter; oversize crop clamps to source.
- End-to-end CLI runs (fixed + adaptive) on a synthetic 1920x1080 clip
  with `--crop 1280x720`: all output JPEGs are exactly 1280x720.
