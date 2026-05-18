from PySide6.QtWidgets import QMainWindow, QSplitter, QToolBar, QStatusBar
from PySide6.QtCore import Qt
from pdf2xlsx.gui.pdf_panel import PdfPanel
from pdf2xlsx.gui.xlsx_panel import XlsxPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pdf2xlsx")
        self.resize(1280, 800)
        self._pdf_path = None
        self._tables = []
        self._build_toolbar()
        self._build_central()
        self.setStatusBar(QStatusBar())

    def _build_toolbar(self):
        tb = QToolBar("Main")
        self.addToolBar(tb)

        self.btn_open = tb.addAction("Open PDF")
        self.btn_open.triggered.connect(self._on_open)

        tb.addSeparator()

        self.btn_convert = tb.addAction("Convert")
        self.btn_convert.setEnabled(False)
        self.btn_convert.triggered.connect(self._on_convert)

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
        self.setCentralWidget(self.splitter)

    def _on_open(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf)"
        )
        if path:
            self._pdf_path = path
            self.pdf_panel.load_pdf(path)
            self.btn_convert.setEnabled(True)
            self.btn_save.setEnabled(False)
            self.xlsx_panel.clear()
            self.statusBar().showMessage(f"Loaded: {path}")

    def _on_convert(self):
        from pathlib import Path
        from pdf2xlsx.extractor import extract_tables
        self.statusBar().showMessage("Converting…")
        try:
            self._tables = extract_tables(Path(self._pdf_path))
            self.xlsx_panel.load_tables(self._tables)
            self.btn_save.setEnabled(True)
            self.statusBar().showMessage(
                f"Extracted {len(self._tables)} table(s)"
            )
        except Exception as exc:
            self.statusBar().showMessage(f"Error: {exc}")

    def _on_save(self):
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path
        from pdf2xlsx.writer import write_xlsx
        path, _ = QFileDialog.getSaveFileName(
            self, "Save XLSX", "", "Excel Files (*.xlsx)"
        )
        if path:
            write_xlsx(self._tables, Path(path))
            self.statusBar().showMessage(f"Saved: {path}")
