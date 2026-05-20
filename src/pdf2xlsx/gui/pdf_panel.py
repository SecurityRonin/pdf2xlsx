import fitz  # pymupdf
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QSizePolicy,
)
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import Qt, Signal


class PdfPanel(QWidget):
    pdf_dropped = Signal(str)   # local file path of the dropped PDF
    page_changed = Signal(int)  # 1-based page number after each navigation

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = None
        self.current_page = 0
        self._zoom = 1.5
        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_prev.setEnabled(False)
        self.lbl_page = QLabel("No document")
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self._next_page)
        self.btn_next.setEnabled(False)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.lbl_page, 1)
        nav.addWidget(self.btn_next)
        layout.addLayout(nav)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.lbl_img = QLabel()
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.scroll.setWidget(self.lbl_img)
        layout.addWidget(self.scroll, 1)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith(".pdf"):
                event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(".pdf"):
                self.pdf_dropped.emit(path)
                event.acceptProposedAction()

    def load_pdf(self, path: str):
        if self._doc:
            self._doc.close()
        self._doc = fitz.open(path)
        self.current_page = 0
        self._render()

    def _render(self):
        if not self._doc:
            return
        page = self._doc[self.current_page]
        mat = fitz.Matrix(self._zoom, self._zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = QImage(
            pix.samples, pix.width, pix.height,
            pix.stride, QImage.Format.Format_RGB888,
        )
        self.lbl_img.setPixmap(QPixmap.fromImage(img))
        total = len(self._doc)
        self.lbl_page.setText(f"Page {self.current_page + 1} / {total}")
        self.btn_prev.setEnabled(self.current_page > 0)
        self.btn_next.setEnabled(self.current_page < total - 1)
        self.page_changed.emit(self.current_page + 1)

    def go_to_page(self, page: int):
        """Navigate to a 1-based page number."""
        if self._doc:
            idx = page - 1
            if 0 <= idx < len(self._doc):
                self.current_page = idx
                self._render()

    def _prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._render()

    def _next_page(self):
        if self._doc and self.current_page < len(self._doc) - 1:
            self.current_page += 1
            self._render()
