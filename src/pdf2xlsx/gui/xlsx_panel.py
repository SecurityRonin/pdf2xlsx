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
        return f"p.{table.page} · {table.sheet_name}  [{table.source}]"

    def load_tables(self, tables):
        self._tables = sorted(tables, key=lambda t: (t.page, t.index))
        self.combo.blockSignals(True)
        self.combo.clear()
        while self.stack.count():
            self.stack.removeWidget(self.stack.widget(0))
        for t in self._tables:
            tbl = self._make_table(t.rows)
            self.stack.addWidget(tbl)
            self.combo.addItem(self._combo_label(t))
        self.combo.blockSignals(False)
        if self._tables:
            self.combo.setCurrentIndex(0)
            self.stack.setCurrentIndex(0)

    def add_table(self, table):
        """Add or replace a table entry, maintaining ascending (page, index) order.

        Same-page entries are upserted in-place; new pages are inserted at the
        correct sorted position so the combo always reads page 1, 2, 3 …
        """
        for i, existing in enumerate(self._tables):
            if existing.page == table.page and existing.index == table.index:
                self._tables[i] = table
                new_widget = self._make_table(table.rows)
                old_widget = self.stack.widget(i)
                self.stack.removeWidget(old_widget)
                old_widget.deleteLater()
                self.stack.insertWidget(i, new_widget)
                self.combo.setItemText(i, self._combo_label(table))
                if self.combo.currentIndex() == i:
                    self.stack.setCurrentIndex(i)
                return
        # New entry — find sorted insertion position by (page, index)
        key = (table.page, table.index)
        pos = next(
            (i for i, t in enumerate(self._tables) if (t.page, t.index) > key),
            len(self._tables),
        )
        self._tables.insert(pos, table)
        tbl = self._make_table(table.rows)
        self.stack.insertWidget(pos, tbl)
        self.combo.insertItem(pos, self._combo_label(table))

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
