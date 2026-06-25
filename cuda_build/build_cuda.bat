@echo off
REM ===================================================================
REM  Local Windows CUDA build for the DJI Frame Extractor.
REM
REM  Produces a GPU-accelerated onedir zip:
REM     dist\extract-frames-windows-cuda-x64.zip
REM
REM  Prerequisites:
REM    - A Python that has a CUDA-enabled OpenCV (cv2.cuda device count >= 1).
REM      By default this script uses `py -3.10`. Override by setting PY, e.g.:
REM         set PY=C:\path\to\python.exe & build_cuda.bat
REM    - The NVIDIA CUDA toolkit bin on PATH (so PyInstaller can bundle the
REM      cv2 CUDA DLL dependencies). The installed cv2 was built against it.
REM    - Internet access on first run (to fetch ffmpeg).
REM ===================================================================

setlocal ENABLEEXTENSIONS
cd /d "%~dp0"

if "%PY%"=="" set PY=py -3.10

echo.
echo === [1/5] Verify CUDA-enabled cv2 in the build interpreter ===
%PY% -c "import cv2,sys; n=cv2.cuda.getCudaEnabledDeviceCount(); print('cv2',cv2.__version__,'| CUDA devices:',n); sys.exit(0 if n>0 else 1)"
if errorlevel 1 (
    echo [ERROR] The selected Python has no CUDA-enabled OpenCV.
    echo         Point PY at the interpreter whose cv2 reports CUDA devices ^>= 1.
    exit /b 1
)

echo.
echo === [2/5] Ensure PyInstaller + PySide6 (does NOT touch cv2) ===
REM No --upgrade: never let pip pull the CPU opencv-python wheel over the
REM locally built CUDA cv2.
%PY% -m pip install --disable-pip-version-check pyinstaller PySide6
if errorlevel 1 exit /b 1

echo.
echo === [3/5] Fetch NVDEC ffmpeg into bin\ (skipped if present) ===
if exist "bin\ffmpeg.exe" if exist "bin\ffprobe.exe" goto :ffmpeg_ok
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fetch_ffmpeg_cuda.ps1"
if errorlevel 1 (
    echo [ERROR] fetch_ffmpeg_cuda.ps1 failed. Download ffmpeg.exe/ffprobe.exe
    echo         manually into the bin\ folder and re-run.
    exit /b 1
)
if not exist "bin\ffmpeg.exe" (
    echo [ERROR] bin\ffmpeg.exe still missing after fetch. Aborting.
    exit /b 1
)
:ffmpeg_ok

echo.
echo === [4/5] Run PyInstaller ===
if exist "build" rmdir /s /q "build"
if exist "dist"  rmdir /s /q "dist"
%PY% -m PyInstaller build_cuda.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed. Scroll up for details.
    exit /b 1
)

echo.
echo === [5/5] Zip onedir -> dist\extract-frames-windows-cuda-x64.zip ===
powershell -NoProfile -Command "Compress-Archive -Path 'dist\extract-frames' -DestinationPath 'dist\extract-frames-windows-cuda-x64.zip' -Force"
if errorlevel 1 exit /b 1

echo.
echo ===================================================================
echo  Build OK.
echo  Output: %CD%\dist\extract-frames-windows-cuda-x64.zip
echo ===================================================================
dir /b dist
exit /b 0
