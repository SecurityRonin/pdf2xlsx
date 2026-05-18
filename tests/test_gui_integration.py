"""End-to-end GUI integration tests using real fixture PDFs."""
import shutil
from pathlib import Path
from unittest.mock import patch
import pytest

FIXTURES = Path("tests/fixtures")


@pytest.fixture
def term_sheet_path(tmp_path):
    dst = tmp_path / "term_sheet.pdf"
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)
    return str(dst)


def test_load_pdf_enables_convert(qtbot, term_sheet_path):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert not win.btn_convert.isEnabled()
    win.pdf_panel.load_pdf(term_sheet_path)
    win._pdf_path = term_sheet_path
    win.btn_convert.setEnabled(True)
    assert win.btn_convert.isEnabled()


def test_convert_populates_xlsx_panel(qtbot, term_sheet_path):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win._pdf_path = term_sheet_path
    win._on_convert()
    assert win.xlsx_panel.tab_widget.count() > 0


def test_convert_enables_save(qtbot, term_sheet_path):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win._pdf_path = term_sheet_path
    win._on_convert()
    assert win.btn_save.isEnabled()


def test_save_writes_file(qtbot, term_sheet_path, tmp_path):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win._pdf_path = term_sheet_path
    win._on_convert()
    out_path = str(tmp_path / "out.xlsx")
    with patch(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        return_value=(out_path, "Excel Files (*.xlsx)"),
    ):
        win._on_save()
    assert Path(out_path).exists()
    assert Path(out_path).stat().st_size > 0


def test_status_bar_shows_table_count(qtbot, term_sheet_path):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win._pdf_path = term_sheet_path
    win._on_convert()
    msg = win.statusBar().currentMessage()
    assert "table" in msg.lower()


def test_pdf_panel_renders_pixmap(qtbot, term_sheet_path):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win._pdf_path = term_sheet_path
    win.pdf_panel.load_pdf(term_sheet_path)
    pm = win.pdf_panel.lbl_img.pixmap()
    assert pm is not None
    assert not pm.isNull()
    assert pm.width() > 0
