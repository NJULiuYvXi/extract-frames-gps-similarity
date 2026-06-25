#!/usr/bin/env python3
"""GPS + camera + focal-length EXIF writing via piexif (shared by both modes).

Pure Python -- no exiftool dependency, no path-encoding issues on Windows
with non-ASCII (e.g. Chinese) directory names.
"""

from pathlib import Path

from .imports import _try_import_piexif


def _deg_to_dms_rational(deg_float):
    """Convert decimal degrees to piexif DMS rational tuple."""
    d = int(abs(deg_float))
    m_float = (abs(deg_float) - d) * 60
    m = int(m_float)
    s = (m_float - m) * 60
    # Use high denominator for sub-arcsecond precision.
    return ((d, 1), (m, 1), (int(round(s * 10000)), 10000))


def _write_gps_exif(output_dir: Path, start_number: int, written: int,
                    src_indices, gps_map, stem: str, log,
                    focal_length: float = 24.0,
                    name_prefix: str = "frame"):
    """Write camera metadata + per-frame GPS + focal length using piexif."""
    if written <= 0:
        return

    piexif, err = _try_import_piexif()
    if piexif is None:
        log(f"  ERROR: piexif not installed ({err}). "
            "Install with:  pip install piexif")
        return

    # -- Default camera tags (DJI Mavic 3 / FC3411) -----------------------
    zeroth_ifd = {
        piexif.ImageIFD.Make: b"DJI",
        piexif.ImageIFD.Model: b"FC3411",
        piexif.ImageIFD.Software: b"10.10.46.06",
        piexif.ImageIFD.Orientation: 1,
        piexif.ImageIFD.XResolution: (72, 1),
        piexif.ImageIFD.YResolution: (72, 1),
        piexif.ImageIFD.ResolutionUnit: 2,
        piexif.ImageIFD.YCbCrPositioning: 1,
    }

    fl_num = int(round(focal_length * 100))
    exif_ifd = {
        piexif.ExifIFD.FocalLength: (fl_num, 100),
        piexif.ExifIFD.FocalLengthIn35mmFilm: int(round(focal_length)),
        piexif.ExifIFD.FNumber: (280, 100),
        piexif.ExifIFD.ColorSpace: 1,
        piexif.ExifIFD.ExifVersion: b"0230",
        piexif.ExifIFD.FlashpixVersion: b"0100",
        piexif.ExifIFD.ComponentsConfiguration: b"\x01\x02\x03\x00",
        piexif.ExifIFD.FileSource: b"\x03",
        piexif.ExifIFD.SceneType: b"\x01",
        piexif.ExifIFD.LensSpecification: (
            (2240, 100), (2240, 100), (280, 100), (280, 100),
        ),
        piexif.ExifIFD.DigitalZoomRatio: (100, 100),
        piexif.ExifIFD.Contrast: 0,
        piexif.ExifIFD.Saturation: 0,
        piexif.ExifIFD.Sharpness: 0,
        piexif.ExifIFD.WhiteBalance: 0,
        piexif.ExifIFD.SceneCaptureType: 0,
        piexif.ExifIFD.GainControl: 0,
        piexif.ExifIFD.Flash: 0,
        piexif.ExifIFD.MeteringMode: 1,
        piexif.ExifIFD.LightSource: 1,
        piexif.ExifIFD.ExposureMode: 1,
        piexif.ExifIFD.ExposureProgram: 1,
    }

    gps_ok = 0
    errors = 0
    log(f"  Writing EXIF (camera + GPS + focal {focal_length}mm) "
        f"to {written} frames via piexif...")

    for i in range(written):
        if i >= len(src_indices):
            break
        src_idx = src_indices[i]
        jpg = output_dir / f"{name_prefix}_{start_number + i}.jpg"
        if not jpg.exists():
            continue

        # -- Build per-frame GPS IFD --
        gps = gps_map.get(src_idx)
        gps_ifd = {}
        if gps is not None:
            lat, lon, alt = gps
            gps_ifd = {
                piexif.GPSIFD.GPSVersionID: (2, 3, 0, 0),
                piexif.GPSIFD.GPSLatitudeRef: "N" if lat >= 0 else "S",
                piexif.GPSIFD.GPSLatitude: _deg_to_dms_rational(lat),
                piexif.GPSIFD.GPSLongitudeRef: "E" if lon >= 0 else "W",
                piexif.GPSIFD.GPSLongitude: _deg_to_dms_rational(lon),
                piexif.GPSIFD.GPSAltitudeRef: 0 if alt >= 0 else 1,
                piexif.GPSIFD.GPSAltitude: (int(round(abs(alt) * 1000)), 1000),
            }
            gps_ok += 1

        exif_dict = {
            "0th": zeroth_ifd,
            "Exif": exif_ifd,
            "GPS": gps_ifd,
        }
        try:
            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, str(jpg))
        except Exception as e:  # noqa: BLE001
            errors += 1
            if errors <= 3:
                log(f"    WARNING: piexif failed on {jpg.name}: {e}")

    log(f"  EXIF done. GPS written to {gps_ok}/{written} frames"
        f"{f', {errors} errors' if errors else ''}.")
