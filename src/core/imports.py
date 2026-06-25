#!/usr/bin/env python3
"""Lazy optional imports shared across the core engine.

cv2 / numpy are only required for the adaptive (similarity) mode; piexif is
required for writing EXIF metadata. They are imported lazily so the GUI
starts -- and the fixed-interval mode works -- even on a machine where
opencv-python is not installed.
"""


def _try_import_cv2():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
        return cv2, np, None
    except Exception as e:  # noqa: BLE001
        return None, None, e


def _try_import_piexif():
    try:
        import piexif  # type: ignore
        return piexif, None
    except Exception as e:  # noqa: BLE001
        return None, e
