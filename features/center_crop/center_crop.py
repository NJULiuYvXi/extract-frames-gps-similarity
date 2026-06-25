#!/usr/bin/env python3
"""
Center-crop feature.

Crops the central WxH window out of each video frame. This is a true crop
(pixels outside the window are discarded) -- NOT downsampling -- so the
retained pixels keep their native resolution / level of detail. When an
output resolution (scale) is also configured, the crop is applied first
and the scale operates on the cropped image.

Two integration points, matching the host application's two pipelines:

  ffmpeg pipeline (fixed-interval mode)
      ffmpeg_center_crop_filter(w, h) -> a "crop=..." element for -vf.
      ffmpeg's crop filter centers by default (x=(in_w-out_w)/2,
      y=(in_h-out_h)/2). min(iw,w)/min(ih,h) guards keep ffmpeg from
      erroring out when the requested crop is larger than the source.

  cv2 pipeline (adaptive / similarity mode)
      center_crop_frame(frame, w, h) -> numpy view of the central region,
      clamped to the frame bounds. The host crops immediately after
      decode, so feature detection / overlap estimation run on exactly
      the pixels that get saved.

No third-party imports: frames are cropped with plain numpy slicing, so
this module works with whatever numpy/cv2 the host application loaded.
"""

CROP_PRESETS = [
    "Off", "3840x2160", "2560x1440", "1920x1080", "1280x720", "Custom...",
]


def ffmpeg_center_crop_filter(crop_w: int, crop_h: int) -> str:
    """Build a centered ffmpeg crop filter, clamped to the source size.

    Commas inside min() are escaped (same pattern as the host's select
    filter) so the filtergraph parser does not split the chain on them.
    """
    return (f"crop='min(iw\\,{int(crop_w)})':'min(ih\\,{int(crop_h)})'")


def center_crop_frame(frame, crop_w: int, crop_h: int):
    """Return the central crop_w x crop_h region of an HxWxC numpy frame.

    Clamps to the frame bounds, so a crop larger than the frame returns
    the full frame in that dimension. Returns a view, not a copy.
    """
    h, w = frame.shape[:2]
    cw = min(int(crop_w), w)
    ch = min(int(crop_h), h)
    x0 = (w - cw) // 2
    y0 = (h - ch) // 2
    return frame[y0:y0 + ch, x0:x0 + cw]


def crop_label(crop) -> str:
    """Human-readable label for run logs. crop is (w, h) or None."""
    if crop is None:
        return "off"
    return f"center {crop[0]}x{crop[1]}"
