from __future__ import annotations

import sys
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QTextEdit,
    QFileDialog, QFrame, QSizePolicy, QProgressBar,
)
from PyQt6.QtGui import QFont, QColor, QPalette, QTextCursor
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import config as cfg


# ─────────────────────────────────────────────────────────────────────────────
# Worker thread — runs render() without blocking the UI
# ─────────────────────────────────────────────────────────────────────────────

class _RenderWorker(QThread):
    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)   # success, message

    def __init__(self, excel: str, output: str, title: str, subtitle: str):
        super().__init__()
        self.excel = excel
        self.output = output
        self.title = title
        self.subtitle = subtitle

    def run(self) -> None:
        import io
        import contextlib

        # Redirect stdout so render()'s print() calls appear in the log
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(_LineEmitter(self.log_line)):
                from main import render
                render(
                    excel_path=self.excel,
                    output_path=self.output,
                    title=self.title,
                    subtitle=self.subtitle,
                )
            self.finished.emit(True, f"Saved: {self.output}")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class _LineEmitter:
    """File-like object that emits each line as a Qt signal."""

    def __init__(self, signal: pyqtSignal):
        self._signal = signal
        self._buf = ""

    def write(self, text: str) -> None:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._signal.emit(line)

    def flush(self) -> None:
        if self._buf:
            self._signal.emit(self._buf)
            self._buf = ""


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

_DARK_BG   = "#2b2b2b"
_PANEL_BG  = "#313335"
_BORDER    = "#555555"
_ACCENT    = "#3D5A6C"
_ACCENT_HV = "#4a6d82"
_TEXT      = "#e0e0e0"
_DIM       = "#aaaaaa"
_LOG_BG    = "#1e1e1e"
_LOG_FG    = "#d4d4d4"
_OK_COLOR  = "#4caf50"
_ERR_COLOR = "#f44336"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Generator")
        self.setMinimumSize(600, 520)
        self.resize(640, 560)
        self._worker: _RenderWorker | None = None
        self._apply_palette()
        self._build_ui()

    # ── Palette ──────────────────────────────────────────────────────────────

    def _apply_palette(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {_DARK_BG};
                color: {_TEXT};
            }}
            QLineEdit {{
                background: {_PANEL_BG};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 5px 8px;
                color: {_TEXT};
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {_ACCENT};
            }}
            QPushButton#browse {{
                background: {_PANEL_BG};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                padding: 5px 10px;
                color: {_TEXT};
                font-size: 12px;
            }}
            QPushButton#browse:hover {{
                background: #3c3f41;
                border-color: {_ACCENT};
            }}
            QPushButton#generate {{
                background: {_ACCENT};
                border: none;
                border-radius: 6px;
                padding: 10px 0;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton#generate:hover {{
                background: {_ACCENT_HV};
            }}
            QPushButton#generate:disabled {{
                background: #3a4a55;
                color: #7a8a95;
            }}
            QTextEdit {{
                background: {_LOG_BG};
                color: {_LOG_FG};
                border: none;
                border-radius: 4px;
                font-family: "Courier New", monospace;
                font-size: 10px;
            }}
            QProgressBar {{
                background: {_PANEL_BG};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                height: 6px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: {_ACCENT};
                border-radius: 3px;
            }}
            QLabel#section {{
                color: {_DIM};
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 1px;
            }}
            QLabel#status_ok  {{ color: {_OK_COLOR};  font-size: 12px; }}
            QLabel#status_err {{ color: {_ERR_COLOR}; font-size: 12px; }}
        """)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(14)

        # Title
        title = QLabel("PDF Generator")
        title.setFont(QFont("Helvetica", 18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Generate A3 landscape PDF from Excel file")
        sub.setFont(QFont("Helvetica", 10))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {_DIM};")
        layout.addWidget(sub)

        layout.addWidget(self._hline())

        # Fields
        layout.addWidget(self._section_label("FILES"))
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        self._excel_edit = self._add_file_row(grid, 0, "Excel file:", "xlsx")
        self._output_edit = self._add_save_row(grid, 1, "Output PDF:", "pdf")
        layout.addLayout(grid)

        layout.addWidget(self._section_label("METADATA"))
        meta = QGridLayout()
        meta.setColumnStretch(1, 1)
        meta.setHorizontalSpacing(8)
        meta.setVerticalSpacing(8)

        self._title_edit = self._add_text_row(meta, 0, "Title:", cfg.DEFAULT_TITLE)
        self._sub_edit   = self._add_text_row(meta, 1, "Subtitle:", cfg.DEFAULT_SUBTITLE)
        layout.addLayout(meta)

        layout.addWidget(self._hline())

        # Log
        layout.addWidget(self._section_label("LOG"))
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(110)
        layout.addWidget(self._log)

        # Progress + status
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setObjectName("status_ok")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)

        # Generate button
        self._gen_btn = QPushButton("Generate PDF")
        self._gen_btn.setObjectName("generate")
        self._gen_btn.clicked.connect(self._on_generate)
        layout.addWidget(self._gen_btn)

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _hline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {_BORDER};")
        return line

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section")
        return lbl

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFixedWidth(90)
        lbl.setStyleSheet(f"color: {_DIM}; font-size: 12px;")
        return lbl

    def _add_file_row(self, grid: QGridLayout, row: int, label: str, ext: str) -> QLineEdit:
        grid.addWidget(self._label(label), row, 0)
        edit = QLineEdit()
        edit.setPlaceholderText(f"Select .{ext} file…")
        grid.addWidget(edit, row, 1)
        btn = QPushButton("Browse…")
        btn.setObjectName("browse")
        btn.setFixedWidth(80)
        btn.clicked.connect(lambda: self._pick_open(edit, ext))
        grid.addWidget(btn, row, 2)
        return edit

    def _add_save_row(self, grid: QGridLayout, row: int, label: str, ext: str) -> QLineEdit:
        grid.addWidget(self._label(label), row, 0)
        edit = QLineEdit()
        edit.setPlaceholderText(f"Choose output .{ext} path…")
        grid.addWidget(edit, row, 1)
        btn = QPushButton("Save as…")
        btn.setObjectName("browse")
        btn.setFixedWidth(80)
        btn.clicked.connect(lambda: self._pick_save(edit, ext))
        grid.addWidget(btn, row, 2)
        return edit

    def _add_text_row(self, grid: QGridLayout, row: int, label: str, default: str) -> QLineEdit:
        grid.addWidget(self._label(label), row, 0)
        edit = QLineEdit(default)
        grid.addWidget(edit, row, 1, 1, 2)
        return edit

    # ── File dialogs ──────────────────────────────────────────────────────────

    def _pick_open(self, edit: QLineEdit, ext: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select file", str(Path.home()),
            f"{ext.upper()} files (*.{ext});;All files (*)"
        )
        if path:
            edit.setText(path)
            if not self._output_edit.text():
                default_out = str(Path(path).with_suffix(".pdf"))
                self._output_edit.setText(default_out)

    def _pick_save(self, edit: QLineEdit, ext: str) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save file", str(Path.home()),
            f"{ext.upper()} files (*.{ext});;All files (*)"
        )
        if path:
            if not path.lower().endswith(f".{ext}"):
                path += f".{ext}"
            edit.setText(path)

    # ── Generate ──────────────────────────────────────────────────────────────

    def _on_generate(self) -> None:
        excel  = self._excel_edit.text().strip()
        output = self._output_edit.text().strip()
        title  = self._title_edit.text().strip() or cfg.DEFAULT_TITLE
        subtitle = self._sub_edit.text().strip()

        if not excel:
            self._set_status("Please select an Excel file.", error=True)
            return
        if not Path(excel).exists():
            self._set_status(f"File not found: {excel}", error=True)
            return
        if not output:
            self._set_status("Please specify an output PDF path.", error=True)
            return

        self._log.clear()
        self._set_status("")
        self._gen_btn.setEnabled(False)
        self._progress.setVisible(True)

        self._worker = _RenderWorker(excel, output, title, subtitle)
        self._worker.log_line.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _append_log(self, line: str) -> None:
        self._log.append(line)
        self._log.moveCursor(QTextCursor.MoveOperation.End)

    def _on_finished(self, success: bool, message: str) -> None:
        self._progress.setVisible(False)
        self._gen_btn.setEnabled(True)
        self._set_status(message, error=not success)

    def _set_status(self, text: str, error: bool = False) -> None:
        self._status.setText(text)
        self._status.setObjectName("status_err" if error else "status_ok")
        self._status.setStyleSheet(
            f"color: {_ERR_COLOR}; font-size: 12px;"
            if error else
            f"color: {_OK_COLOR}; font-size: 12px;"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
