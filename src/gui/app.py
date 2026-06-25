#!/usr/bin/env python3
"""PySide6 desktop UI for the DJI frame extractor.

A modern replacement for the former Tkinter ``App``. The extraction engine
(``src.core.pipeline.process_all``) is unchanged and runs in an
``ExtractWorker`` QThread; log lines and progress are marshalled back to the
GUI thread via Qt signals (queued connections), and cancellation uses the
same ``threading.Event`` the engine already understood.
"""

import os
import platform
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from features.center_crop.center_crop import CROP_PRESETS
from features.grid_split.grid_split import GRID_PRESETS, parse_grid

from src.core.pipeline import process_all
from src.core.probe import parse_resolution, probe_cv2_cuda, probe_hwaccel
from src.gui.style import STYLESHEET

RES_PRESETS = [
    "Original", "3840x2160", "2560x1440", "1920x1080",
    "1280x720", "960x540", "Custom...",
]
MODES = ["Fixed interval", "Adaptive (similarity)"]
DETECTORS = ["ORB (fast, GPU-capable)", "SIFT (robust, CPU only)"]


# --- Worker thread ----------------------------------------------------------

class ExtractWorker(QThread):
    """Runs process_all off the GUI thread, relaying log/progress via signals."""

    log_line = Signal(str)
    progress = Signal(int, int)
    done = Signal()

    def __init__(self, params, cancel_event):
        super().__init__()
        self._params = params          # 16-tuple matching process_all's args
        self._cancel = cancel_event

    def run(self):
        def log(msg):
            self.log_line.emit(str(msg))

        def set_progress(cur, total):
            self.progress.emit(int(cur), int(total))

        try:
            process_all(*self._params, log, set_progress, self._cancel)
        except Exception as e:  # noqa: BLE001
            self.log_line.emit(f"ERROR: {e}")
        finally:
            self.done.emit()


# --- Main window ------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJI Frame Extractor — GPS EXIF + Similarity")
        self.resize(900, 880)
        self.setMinimumSize(760, 640)
        self.setAcceptDrops(True)

        self.cancel_event = threading.Event()
        self.worker: ExtractWorker | None = None

        self.detected_hwaccel = probe_hwaccel()
        self.cv2_cuda_ok, self.cv2_cuda_info = probe_cv2_cuda()
        self.mode = "fixed"

        self._build_ui()
        self._update_custom_entry_state()
        self._update_crop_entry_state()
        self._update_gpu_status_label()
        self._update_cv2_cuda_label()

    # ------------------------------------------------------------ UI build
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        root.addLayout(self._build_header())

        # Scrollable options region so the window shrinks gracefully.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        opts_host = QWidget()
        opts_col = QVBoxLayout(opts_host)
        opts_col.setContentsMargins(0, 0, 6, 0)
        opts_col.setSpacing(12)
        opts_col.addWidget(self._build_paths())
        opts_col.addWidget(self._build_mode_selector())
        opts_col.addWidget(self._build_mode_stack())
        opts_col.addWidget(self._build_output_options())
        opts_col.addStretch(1)
        scroll.setWidget(opts_host)
        root.addWidget(scroll, 3)

        root.addLayout(self._build_actions())
        root.addWidget(self._build_log(), 2)

    def _build_header(self):
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("DJI Frame Extractor")
        title.setObjectName("TitleLabel")
        subtitle = QLabel(
            "Extract GPS-tagged JPEG frames from DJI footage for COLMAP / "
            "3D Gaussian Splatting / photogrammetry"
        )
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setWordWrap(True)
        col.addWidget(title)
        col.addWidget(subtitle)
        return col

    def _build_paths(self):
        box = QGroupBox("Folders")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText(
            "Folder with .MP4 + matching .SRT  (or drag a folder here)")
        in_row = QHBoxLayout()
        in_row.addWidget(self.input_edit, 1)
        in_btn = QPushButton("Browse…")
        in_btn.clicked.connect(self._pick_in)
        in_row.addWidget(in_btn)
        form.addRow("Input folder:", self._wrap(in_row))

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Where sequential JPEGs are written")
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_edit, 1)
        out_btn = QPushButton("Browse…")
        out_btn.clicked.connect(self._pick_out)
        out_row.addWidget(out_btn)
        form.addRow("Output folder:", self._wrap(out_row))
        return box

    def _build_mode_selector(self):
        box = QGroupBox("Extraction mode")
        col = QVBoxLayout(box)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)

        self.btn_fixed = QPushButton("Fixed interval\nevery Nth frame")
        self.btn_adaptive = QPushButton(
            "Adaptive (similarity)\nkeep ~target % overlap")
        for i, btn in enumerate((self.btn_fixed, self.btn_adaptive)):
            btn.setObjectName("ModeButton")
            btn.setCheckable(True)
            btn.setMinimumHeight(64)
            self.mode_group.addButton(btn, i)
            row.addWidget(btn, 1)
        self.btn_fixed.setChecked(True)
        self.mode_group.idClicked.connect(self._on_mode_changed)
        col.addLayout(row)
        return box

    def _build_mode_stack(self):
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_fixed_page())
        self.mode_stack.addWidget(self._build_adaptive_page())
        return self.mode_stack

    def _build_fixed_page(self):
        box = QGroupBox("Fixed-interval options")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 600)
        self.interval_spin.setValue(1)
        self.interval_spin.setFixedWidth(90)
        hint = QLabel("1 = every frame; 30 = roughly one frame per second")
        hint.setObjectName("SectionHint")
        form.addRow("Frame interval:", self._row(self.interval_spin, hint))
        return box

    def _build_adaptive_page(self):
        box = QGroupBox("Adaptive (similarity) options")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(8)

        self.detector_combo = QComboBox()
        self.detector_combo.addItems(DETECTORS)
        self.detector_combo.currentIndexChanged.connect(
            self._update_cv2_cuda_label)
        form.addRow("Detector:", self.detector_combo)

        self.overlap_spin = QSpinBox()
        self.overlap_spin.setRange(10, 95)
        self.overlap_spin.setValue(70)
        self.overlap_spin.setSuffix(" %")
        self.overlap_spin.setFixedWidth(90)
        ov_hint = QLabel("25–35 % = aggressive thinning · 60–75 % = COLMAP-friendly")
        ov_hint.setObjectName("SectionHint")
        form.addRow("Target overlap:", self._row(self.overlap_spin, ov_hint))

        self.tol_spin = QSpinBox()
        self.tol_spin.setRange(1, 20)
        self.tol_spin.setValue(5)
        self.tol_spin.setPrefix("± ")
        self.tol_spin.setSuffix(" %")
        self.tol_spin.setFixedWidth(90)
        form.addRow("Tolerance:", self.tol_spin)

        self.feat_spin = QSpinBox()
        self.feat_spin.setRange(240, 1920)
        self.feat_spin.setSingleStep(60)
        self.feat_spin.setValue(720)
        self.feat_spin.setSuffix(" px")
        self.feat_spin.setFixedWidth(90)
        feat_hint = QLabel("downsample for detection only — output frames stay full-res")
        feat_hint.setObjectName("SectionHint")
        form.addRow("Feature long side:", self._row(self.feat_spin, feat_hint))

        self.cuda_check = QCheckBox("Use cv2.cuda for ORB (auto-detect)")
        self.cuda_check.toggled.connect(self._update_cv2_cuda_label)
        self.cuda_chip = QLabel("")
        self.cuda_chip.setObjectName("StatusChip")
        cuda_redetect = QPushButton("Re-detect")
        cuda_redetect.clicked.connect(self._redetect_cv2_cuda)
        cuda_row = QHBoxLayout()
        cuda_row.addWidget(self.cuda_check)
        cuda_row.addWidget(self.cuda_chip)
        cuda_row.addStretch(1)
        cuda_row.addWidget(cuda_redetect)
        form.addRow("GPU (ORB):", self._wrap(cuda_row))
        return box

    def _build_output_options(self):
        box = QGroupBox("Output options (apply to both modes)")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(8)

        # Resolution
        self.res_combo = QComboBox()
        self.res_combo.addItems(RES_PRESETS)
        self.res_combo.currentIndexChanged.connect(self._update_custom_entry_state)
        self.res_custom = QLineEdit("1920x1080")
        self.res_custom.setFixedWidth(110)
        form.addRow("Resolution:",
                    self._row(self.res_combo, QLabel("Custom:"), self.res_custom))

        # Crop
        self.crop_combo = QComboBox()
        self.crop_combo.addItems(CROP_PRESETS)
        self.crop_combo.currentIndexChanged.connect(self._update_crop_entry_state)
        self.crop_custom = QLineEdit("1920x1080")
        self.crop_custom.setFixedWidth(110)
        form.addRow("Center crop:",
                    self._row(self.crop_combo, QLabel("Custom:"), self.crop_custom))

        # Grid
        self.grid_combo = QComboBox()
        self.grid_combo.addItems(GRID_PRESETS)
        grid_hint = QLabel("tile each frame; tiles share GPS, focal auto-rescaled")
        grid_hint.setObjectName("SectionHint")
        form.addRow("Grid split:", self._row(self.grid_combo, grid_hint))

        # JPEG quality
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 31)
        self.quality_spin.setValue(2)
        self.quality_spin.setFixedWidth(90)
        q_hint = QLabel("1 = best · 31 = worst")
        q_hint.setObjectName("SectionHint")
        form.addRow("JPEG quality:", self._row(self.quality_spin, q_hint))

        # Focal length
        self.focal_spin = QDoubleSpinBox()
        self.focal_spin.setRange(1.0, 1200.0)
        self.focal_spin.setDecimals(1)
        self.focal_spin.setValue(24.0)
        self.focal_spin.setSuffix(" mm")
        self.focal_spin.setFixedWidth(100)
        f_hint = QLabel("written to EXIF FocalLength + FocalLengthIn35mmFilm")
        f_hint.setObjectName("SectionHint")
        form.addRow("Focal length:", self._row(self.focal_spin, f_hint))

        # GPU decode (fixed only)
        self.gpu_check = QCheckBox("Use GPU decode (Fixed mode only, auto-detect)")
        self.gpu_check.toggled.connect(self._update_gpu_status_label)
        self.gpu_chip = QLabel("")
        self.gpu_chip.setObjectName("StatusChip")
        gpu_redetect = QPushButton("Re-detect")
        gpu_redetect.clicked.connect(self._redetect_gpu)
        gpu_row = QHBoxLayout()
        gpu_row.addWidget(self.gpu_check)
        gpu_row.addWidget(self.gpu_chip)
        gpu_row.addStretch(1)
        gpu_row.addWidget(gpu_redetect)
        form.addRow("GPU decode:", self._wrap(gpu_row))

        # Threads
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 16)
        self.threads_spin.setValue(min(4, os.cpu_count() or 4))
        self.threads_spin.setFixedWidth(90)
        t_hint = QLabel("parallel video processing; 1 = sequential")
        t_hint.setObjectName("SectionHint")
        form.addRow("Worker threads:", self._row(self.threads_spin, t_hint))
        return box

    def _build_actions(self):
        row = QHBoxLayout()
        self.start_btn = QPushButton("Start extraction")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.clicked.connect(self._start)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.status_label = QLabel("Idle.")
        self.status_label.setObjectName("SectionHint")

        prog_col = QVBoxLayout()
        prog_col.setSpacing(2)
        prog_col.addWidget(self.progress)
        prog_col.addWidget(self.status_label)

        row.addWidget(self.start_btn)
        row.addWidget(self.cancel_btn)
        row.addSpacing(12)
        row.addLayout(prog_col, 1)
        return row

    def _build_log(self):
        box = QGroupBox("Log")
        col = QVBoxLayout(box)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(150)
        col.addWidget(self.log_view)
        return box

    # ------------------------------------------------------- small helpers
    @staticmethod
    def _wrap(layout):
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    def _row(self, *widgets):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        for wdg in widgets:
            row.addWidget(wdg)
        row.addStretch(1)
        return self._wrap(row)

    # --------------------------------------------------------- UI state
    def _on_mode_changed(self, idx):
        self.mode = "fixed" if idx == 0 else "adaptive"
        self.mode_stack.setCurrentIndex(idx)

    def _update_custom_entry_state(self):
        self.res_custom.setEnabled(self.res_combo.currentText() == "Custom...")

    def _update_crop_entry_state(self):
        self.crop_custom.setEnabled(self.crop_combo.currentText() == "Custom...")

    def _set_chip(self, chip: QLabel, text: str, kind: str = "neutral"):
        names = {"ok": "StatusChipOk", "warn": "StatusChipWarn"}
        chip.setObjectName(names.get(kind, "StatusChip"))
        chip.setText(text)
        chip.style().unpolish(chip)
        chip.style().polish(chip)

    def _update_gpu_status_label(self):
        if self.detected_hwaccel is None:
            self._set_chip(self.gpu_chip,
                           f"{platform.system()}: no GPU hwaccel detected",
                           "warn" if self.gpu_check.isChecked() else "neutral")
        else:
            self._set_chip(
                self.gpu_chip,
                f"{self.detected_hwaccel['name']} — "
                f"{self.detected_hwaccel['description']}", "ok")

    def _redetect_gpu(self):
        self.detected_hwaccel = probe_hwaccel()
        self._update_gpu_status_label()
        self._append_log(">> Re-detected ffmpeg GPU decode.")

    def _update_cv2_cuda_label(self):
        is_orb = self.detector_combo.currentText().startswith("ORB")
        if not is_orb:
            self._set_chip(self.cuda_chip,
                           "SIFT is CPU-only (cv2 has no GPU SIFT)", "neutral")
            return
        if self.cv2_cuda_ok:
            self._set_chip(self.cuda_chip, self.cv2_cuda_info, "ok")
        elif self.cuda_check.isChecked():
            self._set_chip(self.cuda_chip,
                           self.cv2_cuda_info + " — will fall back to CPU ORB",
                           "warn")
        else:
            self._set_chip(self.cuda_chip, self.cv2_cuda_info, "neutral")

    def _redetect_cv2_cuda(self):
        self.cv2_cuda_ok, self.cv2_cuda_info = probe_cv2_cuda()
        self._update_cv2_cuda_label()
        self._append_log(f">> Re-detected cv2.cuda: {self.cv2_cuda_info}")

    # --------------------------------------------------------- pickers
    def _pick_in(self):
        d = QFileDialog.getExistingDirectory(self, "Select input folder (MP4 + SRT)")
        if d:
            self.input_edit.setText(d)
            if not self.output_edit.text().strip():
                self.output_edit.setText(str(Path(d) / "frames"))

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Select output folder for JPEGs")
        if d:
            self.output_edit.setText(d)

    # --------------------------------------------------------- drag & drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_dir():
                self.input_edit.setText(str(p))
                if not self.output_edit.text().strip():
                    self.output_edit.setText(str(p / "frames"))
                break

    # --------------------------------------------------------- log/progress
    def _append_log(self, msg: str):
        self.log_view.appendPlainText(msg)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_progress(self, current: int, total: int):
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(min(current, total))
        if total > 0:
            pct = 100.0 * current / total
            self.status_label.setText(f"Progress: {current} / {total} ({pct:.1f}%)")
        else:
            self.status_label.setText("Progress: 0 / 0")

    # --------------------------------------------------------- resolve inputs
    def _resolve_resolution(self):
        sel = self.res_combo.currentText()
        if sel == "Original":
            return None
        if sel == "Custom...":
            res = parse_resolution(self.res_custom.text())
            if res is None:
                raise ValueError(
                    f"Invalid custom resolution: {self.res_custom.text()!r}. "
                    "Use format like 1920x1080.")
            return res
        return parse_resolution(sel)

    def _resolve_crop(self):
        sel = self.crop_combo.currentText()
        if sel == "Off":
            return None
        if sel == "Custom...":
            crop = parse_resolution(self.crop_custom.text())
            if crop is None:
                raise ValueError(
                    f"Invalid custom crop size: {self.crop_custom.text()!r}. "
                    "Use format like 1920x1080.")
            return crop
        return parse_resolution(sel)

    # --------------------------------------------------------- run / cancel
    def _start(self):
        in_dir = self.input_edit.text().strip()
        out_dir = self.output_edit.text().strip()
        if not in_dir or not out_dir:
            QMessageBox.critical(self, "Error", "Please pick input and output folders.")
            return
        in_path, out_path = Path(in_dir), Path(out_dir)
        if not in_path.is_dir():
            QMessageBox.critical(self, "Error", f"Input is not a directory:\n{in_dir}")
            return
        try:
            resolution = self._resolve_resolution()
        except ValueError as e:
            QMessageBox.critical(self, "Invalid resolution", str(e))
            return
        try:
            crop = self._resolve_crop()
        except ValueError as e:
            QMessageBox.critical(self, "Invalid crop size", str(e))
            return
        grid_n = parse_grid(self.grid_combo.currentText())

        for tool in ("ffmpeg", "ffprobe"):
            if shutil.which(tool) is None:
                QMessageBox.critical(
                    self, "Missing tool",
                    f"Required tool not found in PATH: {tool}\n\n"
                    "macOS/Linux: brew/apt install ffmpeg\n"
                    "Windows: install from ffmpeg.org and add to PATH.")
                return

        from src.core.imports import _try_import_piexif
        piexif, piexif_err = _try_import_piexif()
        if piexif is None:
            QMessageBox.critical(
                self, "Missing dependency",
                "piexif is required for writing EXIF metadata.\n\n"
                "Install with:\n    pip install piexif\n\n"
                f"(import error: {piexif_err})")
            return

        is_adaptive = self.mode == "adaptive"
        if is_adaptive:
            from src.core.imports import _try_import_cv2
            cv2, np, err = _try_import_cv2()
            if cv2 is None:
                QMessageBox.critical(
                    self, "Missing dependency",
                    "Adaptive mode requires opencv-python.\n\n"
                    "Install with:\n    pip install opencv-python numpy\n\n"
                    f"(import error: {err})")
                return
            mode = "adaptive"
            interval = 1
            target = max(0.05, min(0.95, self.overlap_spin.value() / 100.0))
            tol = max(0.01, min(0.30, self.tol_spin.value() / 100.0))
            detector = "ORB" if self.detector_combo.currentText().startswith("ORB") else "SIFT"
            prefer_cuda = bool(self.cuda_check.isChecked()) and detector == "ORB"
            feature_side = max(240, min(1920, self.feat_spin.value()))
            hwaccel = None
        else:
            mode = "fixed"
            interval = max(1, self.interval_spin.value())
            target = 0.0
            tol = 0.0
            detector = "ORB"
            prefer_cuda = False
            feature_side = 720
            hwaccel = self.detected_hwaccel if self.gpu_check.isChecked() else None
            if self.gpu_check.isChecked() and hwaccel is None:
                if QMessageBox.question(
                    self, "No GPU hwaccel detected",
                    "GPU acceleration is enabled but no supported hwaccel was "
                    "detected on this machine.\n\nContinue with CPU decoding?",
                ) != QMessageBox.Yes:
                    return

        if out_path.exists() and any(out_path.iterdir()):
            if QMessageBox.question(
                self, "Output not empty",
                f"Output folder is not empty:\n{out_path}\n\n"
                "Files with the same name will be overwritten.\nContinue?",
            ) != QMessageBox.Yes:
                return

        quality = max(1, min(31, self.quality_spin.value()))
        focal_length = max(1.0, self.focal_spin.value())
        thread_count = max(1, min(16, self.threads_spin.value()))

        params = (
            in_path, out_path, mode, interval, resolution, crop, grid_n,
            quality, hwaccel, target, tol, detector, prefer_cuda,
            feature_side, focal_length, thread_count,
        )

        self.cancel_event = threading.Event()
        self.log_view.clear()
        self.progress.setValue(0)
        self.status_label.setText("Starting…")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self.worker = ExtractWorker(params, self.cancel_event)
        self.worker.log_line.connect(self._append_log)
        self.worker.progress.connect(self._set_progress)
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def _cancel(self):
        self.cancel_event.set()
        self._append_log(">> Cancel requested.")

    def _on_done(self):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Done.")

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.cancel_event.set()
            self.worker.wait(3000)
        event.accept()


def run():
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setFont(QFont("Segoe UI", 10))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
