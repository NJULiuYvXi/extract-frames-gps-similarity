"""PyInstaller entry-point wrapper for the local Windows CUDA build.

Identical in spirit to cross_build/main_packaged.py: prepend the bundled
``bin/`` (NVDEC ffmpeg + ffprobe) to PATH, then launch the app.
"""

import os
import sys
from pathlib import Path


def _setup_bundled_binaries() -> None:
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        else:
            base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent

    bin_dir = base / "bin"
    if bin_dir.is_dir():
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


_setup_bundled_binaries()

if not getattr(sys, "frozen", False):
    parent = str(Path(__file__).resolve().parent.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)

from extract_frames_with_gps_similarity import main  # noqa: E402


if __name__ == "__main__":
    main()
