import fitz  # pymupdf
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QSizePolicy, QListWidget, QListWidgetItem,
    QSpinBox, QSplitter,
)
from PySide6.QtGui import QPixmap, QImage, QIcon
from PySide6.QtCore import Qt, Signal, QSize, QTimer


_THUMB_ZOOM = 0.22   # renders ~135×174 px for letter — comfortably shows 3-digit labels
_THUMB_W = 135
_THUMB_H = 174


class PdfPanel(QWidget):
    pdf_dropped = Signal(str)   # local file path of the dropped PDF
    page_changed = Signal(int)  # 1-based page number after each navigation

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc = None
        self.current_page = 0
        self._zoom = 1.5
        self._block_thumb_signal = False
        self._thumb_render_idx = 0
        self._thumb_timer = None
        self.setAcceptDrops(True)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        # Left: thumbnail strip (resizable via splitter)
        self.thumb_list = QListWidget()
        self.thumb_list.setMinimumWidth(60)
        self.thumb_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumb_list.setFlow(QListWidget.Flow.TopToBottom)
        self.thumb_list.setWrapping(False)
        self.thumb_list.setIconSize(QSize(_THUMB_W, _THUMB_H))
        self.thumb_list.setSpacing(4)
        self.thumb_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumb_list.currentRowChanged.connect(self._on_thumb_row_changed)
        splitter.addWidget(self.thumb_list)

        # Right: nav bar + page view (in a container widget for the splitter)
        right_widget = QWidget()
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)

        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_prev.setEnabled(False)

        self.spin_page = QSpinBox()
        self.spin_page.setMinimum(1)
        self.spin_page.setMaximum(1)
        self.spin_page.setEnabled(False)
        self.spin_page.valueChanged.connect(self._on_spin_changed)

        self.lbl_total = QLabel("/ 0")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(self._next_page)
        self.btn_next.setEnabled(False)

        nav.addWidget(self.btn_prev)
        nav.addStretch(1)
        nav.addWidget(self.spin_page)
        nav.addWidget(self.lbl_total)
        nav.addStretch(1)
        nav.addWidget(self.btn_next)
        right.addLayout(nav)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.lbl_img = QLabel()
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.scroll.setWidget(self.lbl_img)
        right.addWidget(self.scroll, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([_THUMB_W + 24, 800])   # slightly wider than thumbnail
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 0)   # thumb strip: fixed width on resize
        splitter.setStretchFactor(1, 1)   # page view: absorbs extra space

    # ------------------------------------------------------------------
    # Drag-and-drop
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # PDF loading / rendering
    # ------------------------------------------------------------------

    def load_pdf(self, path: str):
        if self._doc:
            self._doc.close()
        self._doc = fitz.open(path)
        self.current_page = 0
        self._load_thumbnails()
        self._update_spinbox()
        self._render()

    def _load_thumbnails(self):
        """Populate the list with placeholders immediately; render lazily via timer."""
        self.thumb_list.clear()
        n = len(self._doc)
        for i in range(n):
            item = QListWidgetItem(str(i + 1))
            item.setSizeHint(QSize(_THUMB_W + 8, _THUMB_H + 24))
            self.thumb_list.addItem(item)
        self.thumb_list.setCurrentRow(0)
        self._thumb_render_idx = 0
        self._thumb_timer = QTimer(self)
        self._thumb_timer.timeout.connect(self._render_next_thumb_batch)
        self._thumb_timer.start(0)  # yield to event loop between batches

    def _render_next_thumb_batch(self, batch=8):
        """Render up to `batch` thumbnails per event-loop tick."""
        if not self._doc or self._thumb_render_idx >= len(self._doc):
            self._thumb_timer.stop()
            return
        mat = fitz.Matrix(_THUMB_ZOOM, _THUMB_ZOOM)
        end = min(self._thumb_render_idx + batch, len(self._doc))
        for i in range(self._thumb_render_idx, end):
            pix = self._doc[i].get_pixmap(matrix=mat, alpha=False)
            img = QImage(
                pix.samples, pix.width, pix.height,
                pix.stride, QImage.Format.Format_RGB888,
            )
            self.thumb_list.item(i).setIcon(QIcon(QPixmap.fromImage(img)))
        self._thumb_render_idx = end

    def _update_spinbox(self):
        total = len(self._doc) if self._doc else 0
        self.spin_page.blockSignals(True)
        self.spin_page.setMaximum(max(1, total))
        self.spin_page.setValue(self.current_page + 1)
        self.spin_page.setEnabled(total > 0)
        self.spin_page.blockSignals(False)
        self.lbl_total.setText(f"/ {total}")

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
        self.btn_prev.setEnabled(self.current_page > 0)
        self.btn_next.setEnabled(self.current_page < total - 1)

        # Sync spinbox without triggering _on_spin_changed
        self.spin_page.blockSignals(True)
        self.spin_page.setValue(self.current_page + 1)
        self.spin_page.blockSignals(False)

        # Sync thumbnail highlight without triggering navigation
        self._block_thumb_signal = True
        self.thumb_list.setCurrentRow(self.current_page)
        self._block_thumb_signal = False

        self.page_changed.emit(self.current_page + 1)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

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

    def _on_spin_changed(self, value: int):
        if self._doc:
            idx = value - 1
            if 0 <= idx < len(self._doc) and idx != self.current_page:
                self.current_page = idx
                self._render()

    def _on_thumb_row_changed(self, row: int):
        if self._block_thumb_signal:
            return
        if self._doc and 0 <= row < len(self._doc) and row != self.current_page:
            self.current_page = row
            self._render()
