#!/usr/bin/env python3
"""
Output-window geometry shared by features and the focal-length rescale.

Single source of truth for the pixel dimensions produced by center crop
and grid split, so the ffmpeg pipeline, the cv2 pipeline and the EXIF
focal-length computation can never disagree.
"""


def cropped_dims(src_w: int, src_h: int, crop):
    """Dimensions after the center crop, clamped to the source size.

    crop is a (w, h) window or None. Mirrors the clamping in
    features/center_crop (and ffmpeg's min(iw, w) guard).
    """
    if crop is None:
        return int(src_w), int(src_h)
    return min(int(crop[0]), int(src_w)), min(int(crop[1]), int(src_h))


def grid_tile_dims(w: int, h: int, n: int):
    """Per-tile dimensions for an NxN split of a WxH frame.

    Tiles are forced to EVEN dimensions (i.e. the frame is trimmed to a
    multiple of 2N before splitting): ffmpeg's untile cannot split
    4:2:0 chroma planes at odd pixel boundaries, and even tiles keep the
    cv2 path byte-identical to the ffmpeg path. At most 2N-1 pixels are
    trimmed per axis, symmetrically.
    """
    n = int(n)
    return (int(w) // (2 * n)) * 2, (int(h) // (2 * n)) * 2
