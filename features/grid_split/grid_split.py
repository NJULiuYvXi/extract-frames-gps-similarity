#!/usr/bin/env python3
"""
Grid-split feature.

Splits each (optionally center-cropped) frame into an NxN grid of tiles
-- e.g. 2x2 (4 tiles) or 3x3 (9 tiles); a 4K frame split 2x2 yields four
1080p images. Tiles are emitted row-major (left-to-right, top-to-bottom)
and every tile inherits the GPS metadata of its source frame. Any frame
aspect ratio is supported.

Frame dimensions are trimmed symmetrically to a multiple of 2N before
splitting (at most 2N-1 pixels per axis), so all tiles end up the same
EVEN size -- ffmpeg's untile cannot split 4:2:0 chroma planes at odd
pixel boundaries, and the cv2 path mirrors the rule so both pipelines
produce identical tiles (see src/shared/geometry.py). When center crop
is also enabled the host applies the crop FIRST and splits the cropped
image.

Tiles keep their native pixels (this is partitioning, not downsampling),
so the focal length written to EXIF must be rescaled for the reduced
field of view -- see src/shared/focal.py.

Two integration points, matching the host application's two pipelines:

  ffmpeg pipeline (fixed-interval mode)
      ffmpeg_grid_filters(n) -> ["crop=...", "untile=NxN"] -vf elements.
      The crop trims to N-divisible dimensions (untile requires exact
      divisibility); untile then turns every input frame into N*N
      sequential output frames, row-major -- so the image2 muxer numbers
      tiles consecutively. Requires ffmpeg >= 4.4 (untile filter).

  cv2 pipeline (adaptive / similarity mode)
      split_frame(frame, n) -> list of N*N numpy views, row-major, with
      the same symmetric edge trim as the ffmpeg path.
"""

import re

from src.shared.geometry import grid_tile_dims

GRID_PRESETS = ["Off", "2x2 (4 tiles)", "3x3 (9 tiles)"]

_GRID_RE = re.compile(r"^([2-9])(?:\s*x\s*\1)?(?:\s*\(.*\))?$")


def parse_grid(s):
    """Parse '2x2', '3', or a GRID_PRESETS label -> N, else None.

    Only square grids are accepted ('2x3' is rejected); 'Off' -> None.
    """
    if not s:
        return None
    m = _GRID_RE.match(str(s).strip().lower())
    if not m:
        return None
    return int(m.group(1))


def ffmpeg_grid_filters(n: int):
    """-vf elements that split each frame into NxN tiles (row-major).

    The leading crop trims to 2N-divisible dimensions, centered, so
    every tile is even-sized and untile never has to split 4:2:0 chroma
    at an odd boundary. Comma escaping follows the host's existing
    select/crop filter pattern.
    """
    n = int(n)
    d = 2 * n
    return [
        f"crop='iw-mod(iw\\,{d})':'ih-mod(ih\\,{d})'",
        f"untile={n}x{n}",
    ]


def split_frame(frame, n: int):
    """Split an HxWxC numpy frame into N*N equal tiles, row-major.

    Mirrors the ffmpeg path: dimensions are trimmed symmetrically so
    tiles are even-sized (src/shared/geometry.grid_tile_dims). Returns
    views, not copies.
    """
    n = int(n)
    h, w = frame.shape[:2]
    tw, th = grid_tile_dims(w, h, n)
    x0 = (w - tw * n) // 2
    y0 = (h - th * n) // 2
    tiles = []
    for r in range(n):
        for c in range(n):
            y = y0 + r * th
            x = x0 + c * tw
            tiles.append(frame[y:y + th, x:x + tw])
    return tiles


def grid_label(n) -> str:
    """Human-readable label for run logs. n is int or None."""
    if not n:
        return "off"
    return f"{n}x{n} ({n * n} tiles)"
