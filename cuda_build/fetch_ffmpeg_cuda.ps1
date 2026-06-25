# Download an NVDEC-capable ffmpeg/ffprobe into cuda_build\bin\ for the local
# CUDA build. Uses the BtbN win64-gpl build, which ships CUDA/NVDEC decoders.

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol =
    [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13

$bin = Join-Path $PSScriptRoot "bin"
New-Item -ItemType Directory -Force -Path $bin | Out-Null

$url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
$zip = Join-Path $env:TEMP "ffmpeg-cuda.zip"
$dst = Join-Path $env:TEMP "ffmpeg-cuda-x"

Write-Host "Downloading NVDEC-capable ffmpeg from:`n  $url"
Invoke-WebRequest $url -OutFile $zip -UseBasicParsing

if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Expand-Archive -Force $zip $dst

$ff = Get-ChildItem $dst -Recurse -Filter ffmpeg.exe  | Select-Object -First 1
$fp = Get-ChildItem $dst -Recurse -Filter ffprobe.exe | Select-Object -First 1
if (-not $ff -or -not $fp) { throw "ffmpeg.exe / ffprobe.exe not found in archive" }

Copy-Item -Force $ff.FullName (Join-Path $bin "ffmpeg.exe")
Copy-Item -Force $fp.FullName (Join-Path $bin "ffprobe.exe")

Write-Host "Placed:"
Get-ChildItem $bin | Format-Table Name, Length
