"""GUI unit tests — run headless with pytest-qt."""
import pytest
import shutil
import unittest.mock as mock
from pathlib import Path
from PySide6.QtCore import Qt, QMimeData, QUrl, QThread
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
    assert panel.spin_page.value() == 1


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
    assert panel.combo.count() == 2


def test_xlsx_panel_clear(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    panel.load_tables([
        ExtractedTable(page=1, index=0, rows=[["A"]], source="pdfplumber")
    ])
    panel.clear()
    assert panel.combo.count() == 0


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
    tbl = panel.stack.widget(0)
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
    tbl = panel.stack.widget(0)
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
    tbl = panel.stack.widget(0)
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
    tbl = panel.stack.widget(0)
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

    assert win.xlsx_panel.combo.count() == 1


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
# Table stays within panel / scroll rather than expand
# ---------------------------------------------------------------------------

def test_table_does_not_expand_panel(qtbot):
    """A wide table must not push the right panel beyond its allocated width."""
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    from PySide6.QtWidgets import QAbstractScrollArea
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    wide_row = [f"Column {i} with some text" for i in range(20)]
    panel.load_tables([
        ExtractedTable(page=1, index=0, rows=[wide_row, wide_row], source="pdfplumber")
    ])
    tbl = panel.stack.widget(0)
    policy = tbl.sizeAdjustPolicy()
    assert policy == QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored, (
        "Table must not resize to fit contents — it must scroll instead"
    )


# ---------------------------------------------------------------------------
# Tab ↔ PDF page sync
# ---------------------------------------------------------------------------

def test_xlsx_panel_has_table_selected_signal(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    assert hasattr(panel, "table_selected"), "XlsxPanel must have a table_selected(page) signal"


def test_xlsx_panel_emits_table_selected_on_tab_change(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    tables = [
        ExtractedTable(page=3, index=0, rows=[["A"]], source="pdfplumber"),
        ExtractedTable(page=7, index=0, rows=[["B"]], source="pdfplumber"),
    ]
    panel.load_tables(tables)
    received = []
    panel.table_selected.connect(received.append)
    panel.combo.setCurrentIndex(1)
    assert received == [7], f"Expected table_selected(7), got {received}"


def test_pdf_panel_has_page_changed_signal(qtbot):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    panel = PdfPanel()
    qtbot.addWidget(panel)
    assert hasattr(panel, "page_changed"), "PdfPanel must have a page_changed(page_1based) signal"


def test_pdf_panel_emits_page_changed_on_navigate(qtbot, tmp_path):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "nav.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    received = []
    panel.page_changed.connect(received.append)
    panel.load_pdf(dst)
    qtbot.mouseClick(panel.btn_next, Qt.MouseButton.LeftButton)
    # load emits page 1, next emits page 2
    assert 1 in received and 2 in received, f"Expected pages 1 and 2, got {received}"


def test_tab_click_advances_pdf_page(qtbot, tmp_path):
    """Selecting tab for page 3 must move the PDF viewer to page 3."""
    from pdf2xlsx.gui.main_window import MainWindow
    from pdf2xlsx.models import ExtractedTable
    dst = str(tmp_path / "sync.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    win = MainWindow()
    qtbot.addWidget(win)
    import unittest.mock as mock
    tables = [
        ExtractedTable(page=1, index=0, rows=[["A"]], source="pdfplumber"),
        ExtractedTable(page=3, index=0, rows=[["B"]], source="pdfplumber"),
    ]
    with mock.patch("pdf2xlsx.extractor.extract_tables", return_value=tables):
        win._load_pdf(dst)
        qtbot.waitUntil(lambda: win.btn_save.isEnabled(), timeout=5000)
    win.xlsx_panel.combo.setCurrentIndex(1)  # select entry for page 3
    assert win.pdf_panel.current_page == 2, (  # 0-based: page 3 → index 2
        f"PDF should be on page 3 (index 2), got {win.pdf_panel.current_page}"
    )


def test_pdf_page_change_selects_matching_tab(qtbot, tmp_path):
    """Navigating PDF to a page that has an extracted table must select that tab."""
    from pdf2xlsx.gui.main_window import MainWindow
    from pdf2xlsx.models import ExtractedTable
    dst = str(tmp_path / "sync2.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    win = MainWindow()
    qtbot.addWidget(win)
    import unittest.mock as mock
    tables = [
        ExtractedTable(page=1, index=0, rows=[["A"]], source="pdfplumber"),
        ExtractedTable(page=2, index=0, rows=[["B"]], source="pdfplumber"),
    ]
    with mock.patch("pdf2xlsx.extractor.extract_tables", return_value=tables):
        win._load_pdf(dst)
        qtbot.waitUntil(lambda: win.btn_save.isEnabled(), timeout=5000)
    qtbot.mouseClick(win.pdf_panel.btn_next, Qt.MouseButton.LeftButton)
    assert win.xlsx_panel.combo.currentIndex() == 1, (
        "Navigating to page 2 must select the combo entry for page 2's table"
    )


# ---------------------------------------------------------------------------
# Thumbnail panel
# ---------------------------------------------------------------------------

def test_pdf_panel_thumb_default_width_accommodates_3digit_labels(qtbot):
    """Thumbnail pane default width must leave space for 3-digit page labels."""
    from pdf2xlsx.gui.pdf_panel import _THUMB_W
    assert _THUMB_W >= 130, (
        f"_THUMB_W={_THUMB_W}; must be ≥130 so '237' labels aren't cramped"
    )


def test_pdf_panel_thumb_strip_does_not_auto_widen(qtbot):
    """Thumbnail strip width must stay constant when the PdfPanel is made wider."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    from PySide6.QtWidgets import QSplitter
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.resize(900, 600)
    qtbot.wait(100)
    splitter = panel.thumb_list.parentWidget()
    assert isinstance(splitter, QSplitter)
    thumb_w = splitter.sizes()[0]
    panel.resize(1400, 600)
    qtbot.wait(100)
    assert splitter.sizes()[0] == thumb_w, (
        f"Thumb strip grew from {thumb_w}px to {splitter.sizes()[0]}px on resize"
    )


def test_main_window_pdf_panel_does_not_auto_widen(qtbot):
    """PDF panel must not absorb extra width when the main window is resized."""
    from pdf2xlsx.gui.main_window import MainWindow
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    win.resize(1200, 800)
    qtbot.wait(100)
    pdf_w = win.splitter.sizes()[0]
    win.resize(1800, 800)
    qtbot.wait(100)
    assert win.splitter.sizes()[0] == pdf_w, (
        f"PDF panel grew from {pdf_w}px to {win.splitter.sizes()[0]}px on resize"
    )


def test_pdf_panel_thumb_strip_resizable(qtbot):
    """The thumbnail strip must live inside a QSplitter so the user can resize it."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    from PySide6.QtWidgets import QSplitter
    panel = PdfPanel()
    qtbot.addWidget(panel)
    assert isinstance(panel.thumb_list.parentWidget(), QSplitter), (
        "thumb_list must be a direct child of a QSplitter for drag-to-resize"
    )


def test_pdf_panel_has_thumbnail_list(qtbot):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    panel = PdfPanel()
    qtbot.addWidget(panel)
    assert hasattr(panel, "thumb_list"), "PdfPanel must have a thumb_list QListWidget"


def test_pdf_panel_thumbnail_count_matches_pages(qtbot, tmp_path):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "multi.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    n_pages = panel._doc.page_count
    assert panel.thumb_list.count() == n_pages, (
        f"Expected {n_pages} thumbnails, got {panel.thumb_list.count()}"
    )


def test_pdf_panel_thumb_click_navigates(qtbot, tmp_path):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "multi.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    panel.thumb_list.setCurrentRow(2)  # click 3rd thumbnail (0-indexed)
    assert panel.current_page == 2, (
        f"Expected page 2 after clicking thumb 2, got {panel.current_page}"
    )


def test_current_thumbnail_highlighted_on_navigate(qtbot, tmp_path):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "multi.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    panel._next_page()
    assert panel.thumb_list.currentRow() == panel.current_page, (
        "Highlighted thumbnail must match current page"
    )


# ---------------------------------------------------------------------------
# Page jump spinbox
# ---------------------------------------------------------------------------

def test_pdf_panel_has_spin_page(qtbot):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    from PySide6.QtWidgets import QSpinBox
    panel = PdfPanel()
    qtbot.addWidget(panel)
    assert hasattr(panel, "spin_page"), "PdfPanel must have a spin_page QSpinBox"
    assert isinstance(panel.spin_page, QSpinBox)


def test_spin_page_range_set_on_load(qtbot, tmp_path):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "multi.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    n_pages = panel._doc.page_count
    assert panel.spin_page.maximum() == n_pages, (
        f"spin_page.maximum() must equal page count ({n_pages})"
    )
    assert panel.spin_page.value() == 1, "spin_page must be 1 after loading"


def test_spin_page_navigates_on_change(qtbot, tmp_path):
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "multi.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    panel.spin_page.setValue(3)
    assert panel.current_page == 2, (  # 0-based
        f"Expected page index 2 after spin_page=3, got {panel.current_page}"
    )


# ---------------------------------------------------------------------------
# Progressive tab display
# ---------------------------------------------------------------------------

def test_xlsx_panel_has_add_table(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    assert callable(getattr(panel, "add_table", None)), "XlsxPanel must have add_table()"


def test_xlsx_panel_add_table_appends_tab(qtbot):
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    t1 = ExtractedTable(page=1, index=0, rows=[["H", "V"], ["a", "1"]], source="pdfplumber")
    t2 = ExtractedTable(page=2, index=0, rows=[["X", "Y"], ["b", "2"]], source="pdfplumber")
    panel.add_table(t1)
    assert panel.combo.count() == 1
    panel.add_table(t2)
    assert panel.combo.count() == 2


def test_worker_emits_table_found_per_table(qtbot, tmp_path):
    """ConversionWorker must emit table_found for each table as it's extracted."""
    from pdf2xlsx.gui.main_window import _ConversionWorker
    from pdf2xlsx.models import ExtractedTable
    dst = str(tmp_path / "prog.pdf")
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)

    fake1 = ExtractedTable(page=1, index=0, rows=[["A", "B"], ["1", "2"]], source="pdfplumber")
    fake2 = ExtractedTable(page=2, index=0, rows=[["C", "D"], ["3", "4"]], source="pdfplumber")

    found = []
    all_tables = [fake1, fake2]

    def fake_extract(path, on_table=None):
        for t in all_tables:
            if on_table:
                on_table(t)
        return all_tables

    with mock.patch("pdf2xlsx.extractor.extract_tables", side_effect=fake_extract):
        worker = _ConversionWorker(dst)
        worker.table_found.connect(found.append)
        thread_obj = QThread()
        worker.moveToThread(thread_obj)
        thread_obj.started.connect(worker.run)
        worker.finished.connect(thread_obj.quit)
        worker.error.connect(thread_obj.quit)
        thread_obj.start()
        # Poll thread state — avoids race where finished signal fires before
        # waitSignal() registers its listener, causing an indefinite hang.
        qtbot.waitUntil(lambda: not thread_obj.isRunning(), timeout=5000)
        thread_obj.wait()
        # Flush any queued cross-thread signals so found.append is called
        qtbot.waitUntil(lambda: len(found) == 2, timeout=2000)

    assert len(found) == 2, f"Expected 2 table_found emissions, got {len(found)}"


# ---------------------------------------------------------------------------
# Right panel: QComboBox replaces QTabWidget
# ---------------------------------------------------------------------------

def test_xlsx_panel_has_combo(qtbot):
    """XlsxPanel must expose a QComboBox as the table selector."""
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from PySide6.QtWidgets import QComboBox
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    assert isinstance(getattr(panel, "combo", None), QComboBox), (
        "XlsxPanel must have a .combo QComboBox attribute"
    )


def test_xlsx_panel_combo_full_width(qtbot):
    """Combo box must expand to fill the full pane width."""
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from PySide6.QtWidgets import QSizePolicy
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    hp = panel.combo.sizePolicy().horizontalPolicy()
    assert hp == QSizePolicy.Policy.Expanding, (
        "Combo box horizontal policy must be Expanding so it fills the pane width"
    )


def test_xlsx_panel_combo_shows_page_and_caption(qtbot):
    """Each combo entry must contain the page number and a table caption."""
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    table = ExtractedTable(page=5, index=0, rows=[["H"], ["v"]], source="pdfplumber")
    panel.add_table(table)
    item_text = panel.combo.itemText(0)
    assert "5" in item_text, f"Combo item must contain page number 5, got: {item_text!r}"


def test_xlsx_panel_combo_selection_changes_stack(qtbot):
    """Selecting a different combo item must switch the visible stack widget."""
    from pdf2xlsx.gui.xlsx_panel import XlsxPanel
    from pdf2xlsx.models import ExtractedTable
    panel = XlsxPanel()
    qtbot.addWidget(panel)
    t1 = ExtractedTable(page=1, index=0, rows=[["A"]], source="pdfplumber")
    t2 = ExtractedTable(page=2, index=0, rows=[["B"]], source="pdfplumber")
    panel.add_table(t1)
    panel.add_table(t2)
    panel.combo.setCurrentIndex(1)
    assert panel.stack.currentIndex() == 1, (
        "stack.currentIndex must follow combo.currentIndex"
    )


# ---------------------------------------------------------------------------
# Zoom controls
# ---------------------------------------------------------------------------

def test_pdf_panel_has_zoom_in_button(qtbot):
    """PdfPanel must have a btn_zoom_in button."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    from PySide6.QtWidgets import QPushButton
    panel = PdfPanel()
    qtbot.addWidget(panel)
    assert isinstance(getattr(panel, "btn_zoom_in", None), QPushButton), (
        "PdfPanel must have a .btn_zoom_in QPushButton"
    )


def test_pdf_panel_has_zoom_out_button(qtbot):
    """PdfPanel must have a btn_zoom_out button."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    from PySide6.QtWidgets import QPushButton
    panel = PdfPanel()
    qtbot.addWidget(panel)
    assert isinstance(getattr(panel, "btn_zoom_out", None), QPushButton), (
        "PdfPanel must have a .btn_zoom_out QPushButton"
    )


def test_pdf_panel_zoom_in_increases_zoom(qtbot, tmp_path):
    """Clicking btn_zoom_in must increase the zoom level."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "zoom.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    zoom_before = panel._zoom
    qtbot.mouseClick(panel.btn_zoom_in, Qt.MouseButton.LeftButton)
    assert panel._zoom > zoom_before, (
        f"_zoom must increase after zoom_in; before={zoom_before}, after={panel._zoom}"
    )


def test_pdf_panel_zoom_out_decreases_zoom(qtbot, tmp_path):
    """Clicking btn_zoom_out must decrease the zoom level."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "zoom2.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    zoom_before = panel._zoom
    qtbot.mouseClick(panel.btn_zoom_out, Qt.MouseButton.LeftButton)
    assert panel._zoom < zoom_before, (
        f"_zoom must decrease after zoom_out; before={zoom_before}, after={panel._zoom}"
    )


def test_pdf_panel_zoom_has_label(qtbot):
    """PdfPanel must show a zoom label (e.g. '150%') in the nav bar."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    from PySide6.QtWidgets import QLabel
    panel = PdfPanel()
    qtbot.addWidget(panel)
    assert isinstance(getattr(panel, "lbl_zoom", None), QLabel), (
        "PdfPanel must have a .lbl_zoom QLabel showing the current zoom level"
    )


def test_pdf_panel_zoom_label_reflects_zoom(qtbot, tmp_path):
    """lbl_zoom text must update to reflect the current zoom after zoom_in."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "zoom3.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.load_pdf(dst)
    text_before = panel.lbl_zoom.text()
    qtbot.mouseClick(panel.btn_zoom_in, Qt.MouseButton.LeftButton)
    text_after = panel.lbl_zoom.text()
    assert text_before != text_after, (
        f"lbl_zoom must update when zoom changes; before={text_before!r}, after={text_after!r}"
    )


# ---------------------------------------------------------------------------
# Keyboard navigation
# ---------------------------------------------------------------------------

def test_pdf_panel_right_arrow_advances_page(qtbot, tmp_path):
    """Right arrow key must advance to the next page."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "key1.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.load_pdf(dst)
    assert panel.current_page == 0
    qtbot.keyClick(panel, Qt.Key.Key_Right)
    assert panel.current_page == 1, (
        f"Right arrow must advance page; got {panel.current_page}"
    )


def test_pdf_panel_left_arrow_goes_back(qtbot, tmp_path):
    """Left arrow key from page 2 must return to page 1."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "key2.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.load_pdf(dst)
    panel.go_to_page(2)
    qtbot.keyClick(panel, Qt.Key.Key_Left)
    assert panel.current_page == 0, (
        f"Left arrow must go back; got {panel.current_page}"
    )


def test_pdf_panel_pagedown_advances_page(qtbot, tmp_path):
    """Page Down key must advance to the next page."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "key3.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.load_pdf(dst)
    qtbot.keyClick(panel, Qt.Key.Key_PageDown)
    assert panel.current_page == 1, (
        f"PageDown must advance page; got {panel.current_page}"
    )


def test_pdf_panel_pageup_goes_back(qtbot, tmp_path):
    """Page Up key from page 2 must return to page 1."""
    from pdf2xlsx.gui.pdf_panel import PdfPanel
    dst = str(tmp_path / "key4.pdf")
    shutil.copy(FIXTURES / "annual_report.pdf", dst)
    panel = PdfPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.load_pdf(dst)
    panel.go_to_page(2)
    qtbot.keyClick(panel, Qt.Key.Key_PageUp)
    assert panel.current_page == 0, (
        f"PageUp must go back; got {panel.current_page}"
    )


# ---------------------------------------------------------------------------
# Progress bar — determinate 0-100%
# ---------------------------------------------------------------------------

def test_progress_bar_is_determinate_during_conversion(qtbot, tmp_path):
    """Progress bar must switch to a 0-100 range (not indeterminate) during conversion."""
    from pdf2xlsx.gui.main_window import MainWindow
    dst = str(tmp_path / "prog2.pdf")
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)
    win = MainWindow()
    qtbot.addWidget(win)

    import threading
    barrier = threading.Event()

    def slow_extract(path, on_table=None, on_progress=None):
        barrier.wait(timeout=3)
        from pdf2xlsx.models import ExtractedTable
        return [ExtractedTable(page=1, index=0, rows=[["X"]], source="pdfplumber")]

    with mock.patch("pdf2xlsx.extractor.extract_tables", side_effect=slow_extract):
        win._load_pdf(dst)
        assert win.progress_bar.maximum() == 100, (
            f"Progress bar must have range 0-100 during conversion, "
            f"got maximum={win.progress_bar.maximum()}"
        )
        barrier.set()
        qtbot.waitUntil(lambda: not win._thread.isRunning(), timeout=5000)


def test_progress_bar_reaches_100_on_completion(qtbot, tmp_path):
    """Progress bar must be at 100% after conversion finishes."""
    from pdf2xlsx.gui.main_window import MainWindow
    from pdf2xlsx.models import ExtractedTable
    dst = str(tmp_path / "prog3.pdf")
    shutil.copy(FIXTURES / "term_sheet.pdf", dst)
    win = MainWindow()
    qtbot.addWidget(win)

    fake = [ExtractedTable(page=1, index=0, rows=[["A", "B"], ["1", "2"]], source="pdfplumber")]
    with mock.patch("pdf2xlsx.extractor.extract_tables", return_value=fake):
        win._load_pdf(dst)
        qtbot.waitUntil(lambda: win.btn_save.isEnabled(), timeout=5000)

    assert win.progress_bar.value() == 100, (
        f"Progress bar must be 100% after conversion; got {win.progress_bar.value()}"
    )


# ---------------------------------------------------------------------------
# App module
# ---------------------------------------------------------------------------

def test_app_module_importable():
    from pdf2xlsx.gui import app
    assert hasattr(app, "main")
