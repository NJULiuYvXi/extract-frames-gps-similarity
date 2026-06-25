# -*- mode: python ; coding: utf-8 -*-
#
# Cross-platform PyInstaller spec used by .github/workflows/release.yml.
#
# Builds CPU-only executables (the PyPI opencv-python wheel has no CUDA).
# On Windows we build --onedir (shipped as a .zip) and embed a VSVersionInfo
# resource -- both reduce how aggressively Defender / SmartScreen flag the
# unsigned binary. On macOS / Linux we build --onefile.
#
# The CI workflow populates ./cross_build/bin/ with ffmpeg + ffprobe before
# invoking pyinstaller.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

spec_dir = Path(SPECPATH).resolve()
project_dir = spec_dir.parent  # holds extract_frames_with_gps_similarity.py
bin_dir = spec_dir / "bin"

is_windows = sys.platform.startswith("win")
exe_suffix = ".exe" if is_windows else ""

required_bins = [f"ffmpeg{exe_suffix}", f"ffprobe{exe_suffix}"]
binaries = []
for name in required_bins:
    p = bin_dir / name
    if p.exists():
        binaries.append((str(p), "bin"))

datas = []

# Discover the app's own packages + third-party runtime deps. PyInstaller's
# PySide6 hook collects the Qt plugins automatically; we still name the modules
# the app imports lazily so static analysis never misses them.
hiddenimports = (
    collect_submodules("src")
    + collect_submodules("features")
    + ["cv2", "numpy", "piexif", "PySide6"]
)

version_file = spec_dir / "windows_version.txt"
version_arg = str(version_file) if (is_windows and version_file.exists()) else None


a = Analysis(
    ["main_packaged.py"],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)


if is_windows:
    # --- Windows: --onedir (folder) so the workflow can zip it ---
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="extract-frames",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
        version=version_arg,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="extract-frames",
    )
else:
    # --- macOS / Linux: --onefile single binary ---
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="extract-frames",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
