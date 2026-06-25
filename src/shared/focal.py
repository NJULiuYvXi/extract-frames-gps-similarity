#!/usr/bin/env python3
"""
Effective focal length after FOV-reducing operations (crop / grid split).

Shared by features/center_crop and features/grid_split.

The user-entered focal length always describes the ORIGINAL frame.
Cropping or tiling discards pixels and therefore narrows the field of
view, while the focal length in pixels (f_px) of the remaining pixels is
unchanged. Downstream tools (COLMAP and friends) derive f_px from EXIF
as

    f_px = FocalLengthIn35mmFilm / 35 * max(image_w, image_h)

so for f_px to stay correct on a cropped/tiled image, the focal length
tag must be scaled by

    factor = max(source_w, source_h) / max(output_w, output_h)

(the classic crop-factor formula, using the long side per COLMAP's
convention). Examples: 2x2 grid -> factor 2; 3x3 -> factor 3; a
1280x720 center crop of 1920x1080 -> factor 1.5.

Output SCALING (the resolution option) does not change the FOV and needs
no adjustment -- the max(w, h) term in the consumer's formula already
accounts for it. Hence the factor here is computed from pre-scale pixel
dimensions only, via the same geometry helpers the features use
(src/shared/geometry.py), so the EXIF focal always matches the pixels
actually written.
"""

from src.shared.geometry import cropped_dims, grid_tile_dims


def effective_focal(focal_mm: float, src_w: int, src_h: int,
                    crop=None, grid_n=None) -> float:
    """Scale focal_mm for the FOV kept after center crop + NxN split.

    crop is a (w, h) center-crop window or None; grid_n is N or None.
    """
    if int(src_w) <= 0 or int(src_h) <= 0:
        return focal_mm
    w, h = cropped_dims(src_w, src_h, crop)
    if grid_n and int(grid_n) > 1:
        w, h = grid_tile_dims(w, h, grid_n)
    if w <= 0 or h <= 0:
        return focal_mm
    factor = max(int(src_w), int(src_h)) / max(w, h)
    return focal_mm * factor
