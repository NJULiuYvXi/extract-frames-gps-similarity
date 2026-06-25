# -*- mode: python ; coding: utf-8 -*-
#
# Local Windows CUDA build. Invoke via build_cuda.bat with the Python that has
# a CUDA-enabled cv2 (e.g. `py -3.10`). Bundles:
#   - that CUDA cv2 (a single cv2.cp310-win_amd64.pyd), whose CUDA DLL deps
#     (cublas64_11 / cufft64_10 / npp*64_11 / cudart64_110 ...) are resolved by
#     PyInstaller's binary-dependency scan from the CUDA toolkit bin on PATH;
#   - PySide6, numpy, piexif, and the app's src/ + features/ packages;
#   - an NVDEC-capable ffmpeg/ffprobe placed in ./bin by fetch_ffmpeg_cuda.ps1.
#
# Always --onedir (zipped to extract-frames-windows-cuda-x64.zip by the .bat).

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

spec_dir = Path(SPECPATH).resolve()
project_dir = spec_dir.parent  # holds extract_frames_with_gps_similarity.py
bin_dir = spec_dir / "bin"

binaries = []
for name in ("ffmpeg.exe", "ffprobe.exe"):
    p = bin_dir / name
    if p.exists():
        binaries.append((str(p), "bin"))

datas = []
hiddenimports = (
    collect_submodules("src")
    + collect_submodules("features")
    + ["numpy", "piexif"]
)

# Pull in the full cv2 (CUDA) and PySide6 trees, including their binaries.
for pkg in ("cv2", "PySide6"):
    pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_bins
    hiddenimports += pkg_hidden

version_file = spec_dir / "windows_version.txt"
version_arg = str(version_file) if version_file.exists() else None


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
