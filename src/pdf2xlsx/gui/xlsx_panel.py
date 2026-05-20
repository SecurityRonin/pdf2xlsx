from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt
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
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

    def load_tables(self, tables):
        self.tab_widget.clear()
        for t in tables:
            tbl = self._make_table(t.rows)
            self.tab_widget.addTab(tbl, t.sheet_name)

    def clear(self):
        self.tab_widget.clear()

    def _make_table(self, rows) -> QTableWidget:
        if not rows:
            return QTableWidget()
        n_rows = len(rows)
        n_cols = max(len(r) for r in rows)
        tbl = QTableWidget(n_rows, n_cols)
        tbl.setAlternatingRowColors(True)
        tbl.setWordWrap(True)

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
