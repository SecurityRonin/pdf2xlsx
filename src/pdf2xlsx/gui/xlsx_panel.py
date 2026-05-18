from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont


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

        header_font = QFont()
        header_font.setBold(True)
        header_bg = QColor("#1f4e79")
        header_fg = QColor("white")

        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                item = QTableWidgetItem(str(cell) if cell else "")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if r == 0:
                    item.setBackground(header_bg)
                    item.setForeground(header_fg)
                    item.setFont(header_font)
                tbl.setItem(r, c, item)

        tbl.horizontalHeader().hide()
        tbl.verticalHeader().hide()
        tbl.resizeColumnsToContents()
        return tbl
