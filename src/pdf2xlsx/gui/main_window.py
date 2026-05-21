from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QToolBar, QStatusBar, QProgressBar, QFileDialog,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal

from pdf2xlsx.gui.pdf_panel import PdfPanel
from pdf2xlsx.gui.xlsx_panel import XlsxPanel


class _ConversionWorker(QObject):
    table_found = Signal(object)   # emitted per table as extraction progresses
    progress = Signal(int, int)    # (current_page, total_pages) during pdfplumber pass
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def run(self):
        from pdf2xlsx.extractor import extract_tables
        try:
            tables = extract_tables(
                Path(self._path),
                on_table=self.table_found.emit,
                on_progress=self.progress.emit,
            )
            self.finished.emit(tables)
        except Exception as exc:
            self.error.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pdf2xlsx")
        self.resize(1280, 800)
        self._pdf_path = None
        self._tables = []
        self._thread = None
        self._worker = None
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

    def _build_toolbar(self):
        tb = QToolBar("Main")
        self.addToolBar(tb)

        self.btn_open = tb.addAction("Open PDF")
        self.btn_open.triggered.connect(self._on_open)

        tb.addSeparator()

        self.btn_save = tb.addAction("Save XLSX")
        self.btn_save.setEnabled(False)
        self.btn_save.triggered.connect(self._on_save)

    def _build_central(self):
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.pdf_panel = PdfPanel()
        self.xlsx_panel = XlsxPanel()
        self.splitter.addWidget(self.pdf_panel)
        self.splitter.addWidget(self.xlsx_panel)
        self.splitter.setSizes([640, 640])
        self.splitter.setStretchFactor(0, 0)   # PDF panel: fixed width on resize
        self.splitter.setStretchFactor(1, 1)   # XLSX panel: absorbs extra space
        self.setCentralWidget(self.splitter)
        self._syncing = False
        self.pdf_panel.pdf_dropped.connect(self._load_pdf)
        self.xlsx_panel.table_selected.connect(self._on_table_selected)
        self.pdf_panel.page_changed.connect(self._on_page_changed)

    def _build_statusbar(self):
        sb = QStatusBar()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)   # indeterminate spinner
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        sb.addPermanentWidget(self.progress_bar)
        self.setStatusBar(sb)

    # ------------------------------------------------------------------
    # Load + convert
    # ------------------------------------------------------------------

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf)"
        )
        if path:
            self._load_pdf(path)

    def _load_pdf(self, path: str):
        """Common entry point for toolbar Open and drag-and-drop."""
        self._pdf_path = path
        self.pdf_panel.load_pdf(path)
        self.btn_save.setEnabled(False)
        self.xlsx_panel.clear()
        self.statusBar().showMessage(f"Loaded: {path}")
        self._start_conversion()

    def _start_conversion(self):
        if not self._pdf_path:
            return
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.btn_save.setEnabled(False)
        self.statusBar().showMessage("Converting…")

        self._worker = _ConversionWorker(self._pdf_path)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.table_found.connect(self.xlsx_panel.add_table)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_conversion_done)
        self._worker.error.connect(self._on_conversion_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_progress(self, current: int, total: int):
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))

    def _on_conversion_done(self, tables):
        self._tables = tables
        # Progressive display adds tabs via table_found; fall back to load_tables
        # if on_table was never called (e.g. in tests that mock extract_tables).
        if self.xlsx_panel.combo.count() == 0 and tables:
            self.xlsx_panel.load_tables(tables)
        self.btn_save.setEnabled(True)
        self.progress_bar.setValue(100)
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(f"Extracted {len(tables)} table(s)")

    def _on_conversion_error(self, msg):
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(f"Error: {msg}")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _on_save(self):
        from pdf2xlsx.writer import write_xlsx
        default = str(Path(self._pdf_path).with_suffix(".xlsx")) if self._pdf_path else ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save XLSX", default, "Excel Files (*.xlsx)"
        )
        if path:
            write_xlsx(self._tables, Path(path))
            self.statusBar().showMessage(f"Saved: {path}")

    # ------------------------------------------------------------------
    # Tab ↔ PDF page sync
    # ------------------------------------------------------------------

    def _on_table_selected(self, page: int):
        if self._syncing:
            return
        self._syncing = True
        self.pdf_panel.go_to_page(page)
        self._syncing = False

    def _on_page_changed(self, page: int):
        if self._syncing:
            return
        self._syncing = True
        self.xlsx_panel.select_page(page)
        self._syncing = False

    # backward-compat alias
    def _on_convert(self):
        self._start_conversion()
