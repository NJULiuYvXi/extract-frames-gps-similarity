"""Modern Qt stylesheet (light theme, blue accent) for the PySide6 UI.

Kept as a Python string rather than a bundled .qss file so PyInstaller has
no extra data file to collect.
"""

STYLESHEET = """
* {
    font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
    font-size: 10pt;
}
QWidget {
    background-color: #f4f6fb;
    color: #1f2933;
}
QMainWindow, QDialog { background-color: #f4f6fb; }

QLabel#TitleLabel { font-size: 19pt; font-weight: 700; color: #0f172a; }
QLabel#SubtitleLabel { color: #64748b; font-size: 9pt; }
QLabel#HintLabel { color: #94a3b8; font-size: 8.5pt; }
QLabel#SectionHint { color: #64748b; font-size: 9pt; }

QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    margin-top: 16px;
    padding: 14px 16px 16px 16px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: #2563eb;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #2563eb;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled {
    background: #f1f5f9; color: #94a3b8;
}
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    border: 1px solid #cbd5e1; background: #ffffff;
    selection-background-color: #2563eb; selection-color: #ffffff;
}

QPushButton {
    background-color: #e2e8f0;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #dbe3ef; }
QPushButton:pressed { background-color: #cbd5e1; }
QPushButton:disabled { background-color: #f1f5f9; color: #b6c0cd; }

QPushButton#PrimaryButton {
    background-color: #2563eb; color: #ffffff; border: none;
    font-weight: 600; padding: 9px 26px;
}
QPushButton#PrimaryButton:hover { background-color: #1d4ed8; }
QPushButton#PrimaryButton:pressed { background-color: #1e40af; }
QPushButton#PrimaryButton:disabled { background-color: #9db8f3; color: #eef2ff; }

QPushButton#DangerButton {
    background-color: #ffffff; color: #dc2626; border: 1px solid #fca5a5;
    font-weight: 600; padding: 9px 22px;
}
QPushButton#DangerButton:hover { background-color: #fef2f2; }
QPushButton#DangerButton:disabled { color: #cbd5e1; border-color: #e5e7eb; }

QPushButton#ModeButton {
    background: #ffffff; border: 1px solid #cbd5e1; border-radius: 9px;
    padding: 8px 18px; text-align: left; font-weight: 600; color: #334155;
}
QPushButton#ModeButton:hover { border-color: #93b4f5; }
QPushButton#ModeButton:checked {
    background: #eff6ff; border: 2px solid #2563eb; color: #1d4ed8;
}

QProgressBar {
    border: none; border-radius: 7px; background: #e2e8f0;
    min-height: 16px; max-height: 16px; text-align: center;
    color: #1f2933; font-size: 8.5pt;
}
QProgressBar::chunk { background-color: #2563eb; border-radius: 7px; }

QPlainTextEdit#LogView {
    background: #0f172a; color: #cbd5e1;
    font-family: "Cascadia Mono", "Consolas", "Courier New", monospace;
    font-size: 9pt; border: 1px solid #1e293b; border-radius: 8px;
    padding: 8px;
}

QLabel#StatusChip {
    color: #475569; background: #f1f5f9; border: 1px solid #e2e8f0;
    border-radius: 5px; padding: 3px 9px; font-size: 8.5pt;
}
QLabel#StatusChipOk {
    color: #15803d; background: #f0fdf4; border: 1px solid #bbf7d0;
    border-radius: 5px; padding: 3px 9px; font-size: 8.5pt;
}
QLabel#StatusChipWarn {
    color: #b45309; background: #fffbeb; border: 1px solid #fde68a;
    border-radius: 5px; padding: 3px 9px; font-size: 8.5pt;
}

QCheckBox { spacing: 7px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical {
    background: #cbd5e1; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #94a3b8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
