from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QStackedWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont


_MAX_COL_WIDTH = 320  # px — cap so no single column dominates the view


def _col_letter(n: int) -> str:
    """Excel-style column label: 0→A, 25→Z, 26→AA …"""
    label = ""
    while True:
        label = chr(ord("A") + n % 26) + label
        n = n // 26 - 1
        if n < 0:
            break
    return label


class XlsxPanel(QWidget):
    table_selected = Signal(int)   # 1-based page number of the active entry

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tables = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.combo = QComboBox()
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.combo)

        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        layout.addWidget(self.stack, 1)

    def _combo_label(self, table) -> str:
        return f"p.{table.page} · {table.sheet_name}"

    def load_tables(self, tables):
        self._tables = list(tables)
        self.combo.blockSignals(True)
        self.combo.clear()
        # Remove all stacked pages
        while self.stack.count():
            self.stack.removeWidget(self.stack.widget(0))
        for t in tables:
            tbl = self._make_table(t.rows)
            self.stack.addWidget(tbl)
            self.combo.addItem(self._combo_label(t))
        self.combo.blockSignals(False)
        if self._tables:
            self.combo.setCurrentIndex(0)
            self.stack.setCurrentIndex(0)

    def add_table(self, table):
        """Append a single table entry (used for progressive display)."""
        self._tables.append(table)
        tbl = self._make_table(table.rows)
        self.stack.addWidget(tbl)
        self.combo.addItem(self._combo_label(table))

    def clear(self):
        self._tables = []
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.blockSignals(False)
        while self.stack.count():
            self.stack.removeWidget(self.stack.widget(0))

    def select_page(self, page: int):
        """Select the first entry whose table is on the given 1-based page."""
        for i, t in enumerate(self._tables):
            if t.page == page:
                self.combo.blockSignals(True)
                self.combo.setCurrentIndex(i)
                self.stack.setCurrentIndex(i)
                self.combo.blockSignals(False)
                break

    def _on_combo_changed(self, index: int):
        if 0 <= index < len(self._tables):
            self.stack.setCurrentIndex(index)
            self.table_selected.emit(self._tables[index].page)

    def _make_table(self, rows) -> QTableWidget:
        if not rows:
            return QTableWidget()
        n_rows = len(rows)
        n_cols = max(len(r) for r in rows)
        tbl = QTableWidget(n_rows, n_cols)
        tbl.setAlternatingRowColors(True)
        tbl.setWordWrap(True)
        tbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        tbl.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)

        # Excel-style column letter headers (A, B, C …)
        tbl.setHorizontalHeaderLabels([_col_letter(c) for c in range(n_cols)])
        hh = tbl.horizontalHeader()
        hh.setVisible(True)
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(40)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        tbl.verticalHeader().hide()

        header_font = QFont()
        header_font.setBold(True)
        header_bg = QColor("#1f4e79")
        header_fg = QColor("white")

        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                text = str(cell) if cell is not None else ""
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if r == 0:
                    item.setBackground(header_bg)
                    item.setForeground(header_fg)
                    item.setFont(header_font)
                tbl.setItem(r, c, item)

        # Size columns to content, then cap any that are too wide
        tbl.resizeColumnsToContents()
        for col in range(n_cols):
            if tbl.columnWidth(col) > _MAX_COL_WIDTH:
                tbl.setColumnWidth(col, _MAX_COL_WIDTH)

        tbl.resizeRowsToContents()
        return tbl
