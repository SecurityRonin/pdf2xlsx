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


# ---------------------------------------------------------------------------
# App module
# ---------------------------------------------------------------------------

def test_app_module_importable():
    from pdf2xlsx.gui import app
    assert hasattr(app, "main")
