"""GUI unit tests — run headless with pytest-qt."""
import pytest
import shutil
import unittest.mock as mock
from pathlib import Path
from PySide6.QtCore import Qt, QMimeData, QUrl
from PySide6.QtGui import QDropEvent, QDragEnterEvent

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
# Drag-and-drop
# ---------------------------------------------------------------------------

def test_pdf_panel_accepts_drops(qtbot):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    panel = PdfPanel()
    qtbot.addWidget(panel)
    assert panel.acceptDrops(), "PdfPanel must accept file drops"


def test_pdf_panel_has_pdf_dropped_signal(qtbot):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    panel = PdfPanel()
    qtbot.addWidget(panel)
    assert hasattr(panel, "pdf_dropped"), "PdfPanel must have a pdf_dropped signal"


def test_pdf_panel_emits_pdf_dropped_on_drop(qtbot, tmp_path):
    """Dropping a PDF file onto PdfPanel must emit pdf_dropped with the path."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "drop.pdf")
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)

    received = []
    panel.pdf_dropped.connect(received.append)

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(dst)])
    # Simulate drop at centre of widget
    pos = panel.rect().center()
    drop_event = QDropEvent(
        pos,
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.dropEvent(drop_event)

    assert received == [dst], f"Expected pdf_dropped('{dst}'), got {received}"


# ---------------------------------------------------------------------------
# Auto-convert + non-blocking progress
# ---------------------------------------------------------------------------

def test_main_window_has_progress_bar(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    from PySide6.QtWidgets import QProgressBar
    win = MainWindow()
    qtbot.addWidget(win)
    assert hasattr(win, "progress_bar"), "MainWindow must have a progress_bar"
    assert isinstance(win.progress_bar, QProgressBar)


def test_progress_bar_hidden_initially(qtbot):
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    assert not win.progress_bar.isVisible(), "Progress bar must be hidden before any PDF is loaded"


def test_auto_convert_on_load(qtbot, tmp_path):
    """Loading a PDF must trigger conversion without a manual Convert click."""
    from pdf2xlsx.gui.main_window import MainWindow
    from pdf2xlsx.models import ExtractedTable
    dst = str(tmp_path / "auto.pdf")
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)
    win = MainWindow()
    qtbot.addWidget(win)

    fake = [ExtractedTable(page=1, index=0, rows=[["A", "B"], ["1", "2"]], source="pdfplumber")]
    with mock.patch("pdf2xlsx.extractor.extract_tables", return_value=fake):
        win._load_pdf(dst)
        # Wait for the background thread to finish
        qtbot.waitUntil(lambda: win.btn_save.isEnabled(), timeout=5000)

    assert win.xlsx_panel.tab_widget.count() == 1


def test_conversion_runs_in_background(qtbot, tmp_path):
    """_start_conversion must not block: the thread is alive immediately after the call."""
    from pdf2xlsx.gui.main_window import MainWindow
    dst = str(tmp_path / "bg.pdf")
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)
    win = MainWindow()
    qtbot.addWidget(win)

    import threading
    barrier = threading.Event()

    def slow_extract(_path):
        barrier.wait(timeout=3)
        from pdf2xlsx.models import ExtractedTable
        return [ExtractedTable(page=1, index=0, rows=[["X"]], source="pdfplumber")]

    with mock.patch("pdf2xlsx.extractor.extract_tables", side_effect=slow_extract):
        win._load_pdf(dst)
        # Thread must be running while the "slow" extract holds on barrier
        assert win._thread is not None and win._thread.isRunning(), (
            "Conversion must run in a background thread (non-blocking)"
        )
        barrier.set()  # unblock the worker
        qtbot.waitUntil(lambda: not win._thread.isRunning(), timeout=5000)


def test_drag_drop_triggers_conversion(qtbot, tmp_path):
    """Dropping a PDF on the left panel must auto-convert (Save button enabled after)."""
    from pdf2xlsx.gui.main_window import MainWindow
    from pdf2xlsx.models import ExtractedTable
    dst = str(tmp_path / "drop_conv.pdf")
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)
    win = MainWindow()
    qtbot.addWidget(win)

    fake = [ExtractedTable(page=1, index=0, rows=[["H"], ["v"]], source="pdfplumber")]
    with mock.patch("pdf2xlsx.extractor.extract_tables", return_value=fake):
        # Simulate the signal that the drop event fires
        win.pdf_panel.pdf_dropped.emit(dst)
        qtbot.waitUntil(lambda: win.btn_save.isEnabled(), timeout=5000)

    assert win._pdf_path == dst


# ---------------------------------------------------------------------------
# App module
# ---------------------------------------------------------------------------

def test_app_module_importable():
    from pdf2xlsx.gui import app
    assert hasattr(app, "main")
