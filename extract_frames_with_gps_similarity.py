#!/usr/bin/env python3
"""DJI drone video -> sequential JPEG frames with GPS EXIF metadata.

Thin entry point. The application was refactored out of a single 1800-line
module into packages:

  src/core/   -- UI-agnostic extraction engine (SRT, probing, overlap,
                 fixed/adaptive extractors, EXIF, the process_all driver)
  src/cli.py  -- headless command-line interface (the ``--cli`` mode)
  src/gui/    -- PySide6 desktop UI
  features/   -- center_crop, grid_split (optional per-frame operations)
  src/shared/ -- geometry + focal-length helpers

Usage:
  GUI:  python extract_frames_with_gps_similarity.py
  CLI:  python extract_frames_with_gps_similarity.py --cli fixed    IN OUT [...]
        python extract_frames_with_gps_similarity.py --cli adaptive IN OUT [...]

External dependencies:
  - ffmpeg / ffprobe                       (must be on PATH)
  - piexif                                 (EXIF writing)
  - opencv-python or a CUDA OpenCV build   (+ numpy; adaptive mode only)
  - PySide6                                (GUI only)
"""

import sys
from pathlib import Path

# Make the project root importable as the package root, whether launched as a
# plain script or frozen by PyInstaller.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main():
    if "--cli" in sys.argv:
        from src.cli import main as cli_main
        cli_main()
        return
    from src.gui.app import run
    run()


if __name__ == "__main__":
    main()
