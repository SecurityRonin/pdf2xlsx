"""GUI unit tests — run headless with pytest-qt."""
import pytest
import shutil
from pathlib import Path
from PySide6.QtCore import Qt

FIXTURES = Path("tests/fixtures")


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

def test_main_window_title(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.windowTitle() == "pdf2xlsx"


def test_main_window_has_open_button(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.btn_open is not None


def test_main_window_has_convert_button(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.btn_convert is not None
    assert not win.btn_convert.isEnabled()


def test_main_window_has_save_button(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.btn_save is not None
    assert not win.btn_save.isEnabled()


def test_main_window_has_splitter(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.splitter is not None


def test_main_window_has_pdf_panel(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.pdf_panel is not None


def test_main_window_has_xlsx_panel(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert win.xlsx_panel is not None


# ---------------------------------------------------------------------------
# PdfPanel
# ---------------------------------------------------------------------------

def test_pdf_panel_loads_pdf(qtbot, tmp_path):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "test.pdf")
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    assert panel.lbl_page.text().startswith("Page 1")


def test_pdf_panel_prev_next_buttons(qtbot, tmp_path):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "multi.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    assert panel.current_page == 0
    qtbot.mouseClick(panel.btn_next, Qt.MouseButton.LeftButton)
    assert panel.current_page == 1
    qtbot.mouseClick(panel.btn_prev, Qt.MouseButton.LeftButton)
    assert panel.current_page == 0


# ---------------------------------------------------------------------------
# XlsxPanel
# ---------------------------------------------------------------------------

def test_xlsx_panel_loads_tables(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    tables = [
        ExtractedTable(page=1, index=0, rows=[["A", "B"], ["1", "2"]], source="pdfplumber"),
        ExtractedTable(page=2, index=0, rows=[["X", "Y"], ["3", "4"]], source="pdfplumber"),
    ]
    panel.load_tables(tables)
    assert panel.tab_widget.count() == 2


def test_xlsx_panel_clear(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    panel.load_tables([
        ExtractedTable(page=1, index=0, rows=[["A"]], source="pdfplumber")
    ])
    panel.clear()
    assert panel.tab_widget.count() == 0


def test_xlsx_panel_cell_data(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    panel.load_tables([
        ExtractedTable(
            page=3, index=0,
            rows=[["Name", "Val"], ["Alice", "100"]],
            source="pdfplumber",
        )
    ])
    tbl = panel.tab_widget.widget(0)
    assert tbl.item(0, 0).text() == "Name"
    assert tbl.item(1, 1).text() == "100"


def test_xlsx_panel_columns_resizable(qtbot):
    """Horizontal header must be visible so users can drag column widths."""
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    from PySide6.QtWidgets import QHeaderView
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    panel.load_tables([
        ExtractedTable(page=1, index=0, rows=[["Name", "Value"], ["Alice", "100"]], source="pdfplumber")
    ])
    tbl = panel.tab_widget.widget(0)
    assert not tbl.horizontalHeader().isHidden(), "Header must not be hidden (resize handles need it)"
    mode = tbl.horizontalHeader().sectionResizeMode(0)
    assert mode == QHeaderView.ResizeMode.Interactive, "Columns must be user-resizable"


def test_xlsx_panel_long_text_not_truncated(qtbot):
    """Cells with long text must not be clipped — column wide enough or word-wrapped."""
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    long_text = "This is a very long cell value that would normally be truncated by default column width settings"
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    panel.load_tables([
        ExtractedTable(page=1, index=0, rows=[["Label", "Description"], ["Row1", long_text]], source="pdfplumber")
    ])
    tbl = panel.tab_widget.widget(0)
    col_width = tbl.columnWidth(1)
    # Either column is wide enough to show the text, or word-wrap is on
    assert col_width > 50 or tbl.wordWrap(), "Long text must not be silently clipped"
    # Item text must be complete — no ellipsis in the model
    assert tbl.item(1, 1).text() == long_text


def test_xlsx_panel_unicode_cells(qtbot):
    """CJK, Arabic, and special characters must be stored and retrievable intact."""
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    rows = [
        ["English", "Chinese", "Arabic", "Symbol"],
        ["Hello", "你好世界", "مرحبا", "✓ ✗ →"],
    ]
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    panel.load_tables([
        ExtractedTable(page=1, index=0, rows=rows, source="pdfplumber")
    ])
    tbl = panel.tab_widget.widget(0)
    assert tbl.item(1, 1).text() == "你好世界"
    assert tbl.item(1, 2).text() == "مرحبا"
    assert tbl.item(1, 3).text() == "✓ ✗ →"


# ---------------------------------------------------------------------------
# App module
# ---------------------------------------------------------------------------

def test_app_module_importable():
    from pdf2xlsx.gui import app
    assert hasattr(app, "main")
