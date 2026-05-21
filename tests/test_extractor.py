import pytest
import time
from pathlib import Path
from collections import defaultdict
from unittest.mock import patch, MagicMock
from pdf2xlsx.extractor import (
    extract_tables, _merge_continuation_tables, _select_best_per_page,
    _pages_with_drawn_lines, _IMG2TABLE_ZOOM,
)
from pdf2xlsx.models import ExtractedTable

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_returns_list(annual_report):
    tables = extract_tables(annual_report)
    assert isinstance(tables, list)
    assert all(isinstance(t, ExtractedTable) for t in tables)


def test_annual_report_has_tables(annual_report):
    tables = extract_tables(annual_report)
    assert len(tables) > 0, "Annual report must have at least one table"


def test_tables_have_multiple_rows(annual_report):
    tables = extract_tables(annual_report)
    non_empty = [t for t in tables if not t.is_empty]
    assert len(non_empty) > 0


def test_tables_have_page_numbers(annual_report):
    tables = extract_tables(annual_report)
    for t in tables:
        assert t.page >= 1


def test_esg_report_has_tables(esg_report):
    tables = extract_tables(esg_report)
    assert len(tables) > 0


def test_academic_paper_has_tables(academic_paper):
    tables = extract_tables(academic_paper)
    assert len(tables) > 0


def test_term_sheet_has_tables(term_sheet):
    tables = extract_tables(term_sheet)
    assert len(tables) > 0


def test_extract_nonexistent_file_raises():
    with pytest.raises(FileNotFoundError):
        extract_tables(Path("/nonexistent/file.pdf"))


def test_no_empty_tables_returned(annual_report):
    tables = extract_tables(annual_report)
    for t in tables:
        assert not t.is_empty, f"Empty table returned on page {t.page}"


def test_unique_indices_per_page(annual_report):
    tables = extract_tables(annual_report)
    by_page: dict[int, list[int]] = defaultdict(list)
    for t in tables:
        by_page[t.page].append(t.index)
    for page, indices in by_page.items():
        assert len(indices) == len(set(indices)), (
            f"Duplicate table indices on page {page}: {indices}"
        )


def test_all_rows_are_lists(annual_report):
    tables = extract_tables(annual_report)
    for t in tables:
        for row in t.rows:
            assert isinstance(row, list), f"Row is not a list: {type(row)}"


def test_no_none_in_cells(annual_report):
    tables = extract_tables(annual_report)
    for t in tables:
        for row in t.rows:
            for cell in row:
                assert cell is not None, f"None cell found in table on page {t.page}"


def test_merge_continuation_tables_same_page_merges():
    """Sub-tables on the same page that start with a data row must be merged."""
    header_row = ["Name and Principal Position", "Year", "Salary ($)", "Bonus ($)"]
    t1 = ExtractedTable(page=5, index=0, source="pdfplumber", rows=[
        header_row,
        ["Tim Cook", "2023", "3,000,000", "0"],
        ["Chief Executive Officer", "2022", "3,000,000", "0"],
        ["", "2021", "3,000,000", "0"],
    ])
    t2 = ExtractedTable(page=5, index=1, source="pdfplumber", rows=[
        ["Luca Maestri", "2023", "1,000,000", "0"],
        ["Senior VP, CFO", "2022", "1,000,000", "0"],
        ["", "2021", "1,000,000", "0"],
    ])
    merged = _merge_continuation_tables([t1, t2])
    assert len(merged) == 1, f"Expected 1 merged table, got {len(merged)}"
    assert len(merged[0].rows) == 7, f"Expected 7 rows, got {len(merged[0].rows)}"


def test_merge_continuation_tables_different_pages_not_merged():
    """Tables on different pages must never be merged."""
    t1 = ExtractedTable(page=5, index=0, source="pdfplumber", rows=[
        ["Name", "Year", "Amount"],
        ["Alice", "2023", "100"],
    ])
    t2 = ExtractedTable(page=6, index=0, source="pdfplumber", rows=[
        ["Bob", "2023", "200"],
    ])
    merged = _merge_continuation_tables([t1, t2])
    assert len(merged) == 2, "Tables on different pages must not be merged"


def test_merge_continuation_tables_header_boundary_not_merged():
    """If the second table has a column-header first row, it is a new table."""
    t1 = ExtractedTable(page=5, index=0, source="pdfplumber", rows=[
        ["Item", "Q1", "Q2"],
        ["Revenue", "100", "200"],
    ])
    t2 = ExtractedTable(page=5, index=1, source="pdfplumber", rows=[
        ["Item", "Q3", "Q4"],   # all-text row → header of new table
        ["Revenue", "300", "400"],
    ])
    merged = _merge_continuation_tables([t1, t2])
    assert len(merged) == 2, "Second table with a header row must stay separate"


def test_merge_continuation_tables_different_col_count_not_merged():
    """Tables with different column counts must not be merged."""
    t1 = ExtractedTable(page=5, index=0, source="pdfplumber", rows=[
        ["Name", "Year", "Amount"],
        ["Alice", "2023", "100"],
    ])
    t2 = ExtractedTable(page=5, index=1, source="pdfplumber", rows=[
        ["Bob", "2023", "200", "Extra"],   # 4 cols vs 3
    ])
    merged = _merge_continuation_tables([t1, t2])
    assert len(merged) == 2, "Tables with different column counts must not be merged"


def test_borderless_rows_recovered_via_two_pass(term_sheet):
    """
    Pages where only some table sections have border lines must still recover
    all data rows by using bordered table column positions as explicit guides.

    term_sheet.pdf p.64 has 5 executives × 3 years = 15 data rows, but only
    2 executives have PDF border lines.  After the two-pass fix we expect at
    least 10 rows on that page (some name/header rows may still be split).
    """
    tables = extract_tables(term_sheet)
    p64 = [t for t in tables if t.page == 64]
    total_rows = sum(len(t.rows) for t in p64)
    assert total_rows >= 10, (
        f"Expected ≥10 rows on p.64, got {total_rows} across {len(p64)} table(s). "
        "Borderless rows from executives without PDF border lines may be missing."
    )


# ---------------------------------------------------------------------------
# Five-engine concurrent extraction
# ---------------------------------------------------------------------------

def test_all_five_engines_called(annual_report):
    """extract_tables must invoke all 5 engine functions."""
    called = []
    real_pdfplumber = __import__('pdf2xlsx.extractor', fromlist=['_extract_pdfplumber'])._extract_pdfplumber
    real_pymupdf    = __import__('pdf2xlsx.extractor', fromlist=['_extract_pymupdf'])._extract_pymupdf
    real_cl         = __import__('pdf2xlsx.extractor', fromlist=['_extract_camelot_lattice'])._extract_camelot_lattice
    real_cs         = __import__('pdf2xlsx.extractor', fromlist=['_extract_camelot_stream'])._extract_camelot_stream
    real_i2t        = __import__('pdf2xlsx.extractor', fromlist=['_extract_img2table'])._extract_img2table

    def spy(fn, name):
        def wrapper(*a, **kw):
            called.append(name)
            return fn(*a, **kw)
        return wrapper

    with patch('pdf2xlsx.extractor._extract_pdfplumber',   spy(real_pdfplumber, 'pdfplumber')), \
         patch('pdf2xlsx.extractor._extract_pymupdf',      spy(real_pymupdf,    'pymupdf')), \
         patch('pdf2xlsx.extractor._extract_camelot_lattice', spy(real_cl,      'camelot_lattice')), \
         patch('pdf2xlsx.extractor._extract_camelot_stream',  spy(real_cs,      'camelot_stream')), \
         patch('pdf2xlsx.extractor._extract_img2table',    spy(real_i2t,        'img2table')):
        extract_tables(annual_report)

    assert set(called) == {'pdfplumber', 'pymupdf', 'camelot_lattice', 'camelot_stream', 'img2table'}, (
        f"Expected all 5 engines called, got: {set(called)}"
    )


def test_engines_run_concurrently(annual_report):
    """All 5 engines must run in parallel: wall time < sum of individual delays."""
    DELAY = 0.15  # seconds per engine
    total_sequential = DELAY * 5  # 0.75s if sequential

    def slow_engine(path, **kw):
        time.sleep(DELAY)
        return []

    with patch('pdf2xlsx.extractor._extract_pdfplumber',      slow_engine), \
         patch('pdf2xlsx.extractor._extract_pymupdf',         slow_engine), \
         patch('pdf2xlsx.extractor._extract_camelot_lattice', slow_engine), \
         patch('pdf2xlsx.extractor._extract_camelot_stream',  slow_engine), \
         patch('pdf2xlsx.extractor._extract_img2table',       slow_engine):
        t0 = time.monotonic()
        extract_tables(annual_report)
        elapsed = time.monotonic() - t0

    assert elapsed < total_sequential * 0.6, (
        f"Engines appear sequential: wall time {elapsed:.2f}s ≥ {total_sequential * 0.6:.2f}s threshold"
    )


def test_engine_failure_does_not_crash(annual_report):
    """If one engine raises, extract_tables must still return results from others."""
    def boom(path, **kw):
        raise RuntimeError("simulated engine failure")

    real_pdfplumber = __import__('pdf2xlsx.extractor', fromlist=['_extract_pdfplumber'])._extract_pdfplumber
    with patch('pdf2xlsx.extractor._extract_camelot_lattice', boom), \
         patch('pdf2xlsx.extractor._extract_camelot_stream',  boom), \
         patch('pdf2xlsx.extractor._extract_img2table',       boom):
        tables = extract_tables(annual_report)
    assert isinstance(tables, list), "Must return a list even when engines fail"


def test_select_best_per_page_prefers_more_data():
    """_select_best_per_page must choose the engine with the most non-empty cells."""
    sparse = [ExtractedTable(page=1, index=0, source='a', rows=[
        ['H1', 'H2'], ['', ''], ['', ''],
    ])]
    dense = [ExtractedTable(page=1, index=0, source='b', rows=[
        ['H1', 'H2'], ['v1', 'v2'], ['v3', 'v4'], ['v5', 'v6'],
    ])]
    result = _select_best_per_page({'sparse_engine': sparse, 'dense_engine': dense})
    assert len(result) == 1
    assert result[0].source == 'b', (
        f"Expected dense engine 'b' to win, got '{result[0].source}'"
    )


def test_select_best_per_page_combines_different_pages():
    """Each page uses the best engine independently."""
    eng_a = [ExtractedTable(page=1, index=0, source='a', rows=[['H'], ['v1'], ['v2']])]
    eng_b = [ExtractedTable(page=2, index=0, source='b', rows=[['X'], ['y1'], ['y2']])]
    result = _select_best_per_page({'a': eng_a, 'b': eng_b})
    pages = {t.page: t.source for t in result}
    assert pages == {1: 'a', 2: 'b'}, f"Expected each page from its best engine, got {pages}"


def test_no_stuck_words_in_cells(general_ledger):
    """Cells must not concatenate words without spaces (pdfplumber x_tolerance bug)."""
    tables = extract_tables(general_ledger)
    stuck = [
        (t.page, cell)
        for t in tables
        for row in t.rows
        for cell in row
        if len(cell) > 20
        and ' ' not in cell
        and any(c.isupper() for c in cell[1:])
        and not cell.startswith('$')
        and not cell.replace(',', '').replace('.', '').replace('-', '').isnumeric()
    ]
    assert stuck == [], (
        f"Found {len(stuck)} cell(s) with words stuck together, e.g. {stuck[0]}"
    )


# ---------------------------------------------------------------------------
# img2table render zoom
# ---------------------------------------------------------------------------

def test_img2table_zoom_is_at_most_one():
    """_IMG2TABLE_ZOOM must be ≤ 1.0 to avoid 4× memory/time overhead."""
    assert _IMG2TABLE_ZOOM <= 1.0, (
        f"_IMG2TABLE_ZOOM={_IMG2TABLE_ZOOM}; must be ≤1.0 (was 2.0, causing 4× slowdown)"
    )


# ---------------------------------------------------------------------------
# _pages_with_drawn_lines — line detection for camelot lattice gating
# ---------------------------------------------------------------------------

@pytest.fixture
def pdf_with_rect(tmp_path):
    """Single-page PDF containing a drawn rectangle (simulated table border)."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(50, 50, 300, 200), color=(0, 0, 0), width=1)
    path = tmp_path / "with_rect.pdf"
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def pdf_with_hline(tmp_path):
    """Single-page PDF containing a long horizontal drawn line."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.draw_line(fitz.Point(50, 100), fitz.Point(350, 100), color=(0, 0, 0), width=1)
    path = tmp_path / "with_line.pdf"
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def pdf_text_only(tmp_path):
    """Single-page PDF with only text, no drawn lines."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Hello world\nNo lines here")
    path = tmp_path / "text_only.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_pages_with_drawn_lines_detects_rect(pdf_with_rect):
    """A page with a drawn rectangle must be returned."""
    pages = _pages_with_drawn_lines(pdf_with_rect)
    assert 1 in pages, f"Page 1 (has rect) must be in result, got {pages}"


def test_pages_with_drawn_lines_detects_hline(pdf_with_hline):
    """A page with a long horizontal line must be returned."""
    pages = _pages_with_drawn_lines(pdf_with_hline)
    assert 1 in pages, f"Page 1 (has h-line) must be in result, got {pages}"


def test_pages_with_drawn_lines_empty_on_text_only(pdf_text_only):
    """A text-only page with no drawn lines must not be returned."""
    pages = _pages_with_drawn_lines(pdf_text_only)
    assert 1 not in pages, f"Text-only page must not be detected as having lines, got {pages}"


def test_pages_with_drawn_lines_multipage(tmp_path):
    """Only pages with drawn lines should be returned; text-only pages excluded."""
    import fitz
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((50, 50), "Text only")                              # page 1: no lines
    p2 = doc.new_page()
    p2.draw_rect(fitz.Rect(50, 50, 300, 200), color=(0, 0, 0), width=1)  # page 2: rect
    p3 = doc.new_page()
    p3.insert_text((50, 50), "Also text only")                          # page 3: no lines
    path = tmp_path / "multi.pdf"
    doc.save(str(path))
    doc.close()
    pages = _pages_with_drawn_lines(path)
    assert pages == {2}, f"Expected only page 2, got {pages}"


# ---------------------------------------------------------------------------
# camelot lattice page filtering
# ---------------------------------------------------------------------------

def test_camelot_lattice_skips_all_when_no_lines(tmp_path):
    """camelot_lattice must not call camelot.read_pdf when no pages have drawn lines."""
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "No lines")
    path = tmp_path / "nolines.pdf"
    doc.save(str(path))
    doc.close()

    with patch('camelot.read_pdf') as mock_read:
        from pdf2xlsx.extractor import _extract_camelot_lattice
        result = _extract_camelot_lattice(path)
    mock_read.assert_not_called(), "camelot.read_pdf must not be called on line-free PDF"
    assert result == []


def test_camelot_lattice_passes_only_line_pages(tmp_path):
    """camelot_lattice must call camelot.read_pdf with only pages that have drawn lines."""
    import fitz
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "Text only")                           # p1 no lines
    doc.new_page().draw_rect(fitz.Rect(50,50,300,200), color=(0,0,0), width=1)  # p2 has rect
    doc.new_page().insert_text((50, 50), "Text only")                           # p3 no lines
    path = tmp_path / "filtered.pdf"
    doc.save(str(path))
    doc.close()

    with patch('camelot.read_pdf', return_value=[]) as mock_read:
        from pdf2xlsx.extractor import _extract_camelot_lattice
        _extract_camelot_lattice(path)
    mock_read.assert_called_once()
    call_kwargs = mock_read.call_args
    pages_arg = call_kwargs.kwargs.get('pages') or call_kwargs.args[1]
    assert pages_arg == '2', (
        f"camelot.read_pdf must be called with pages='2', got pages={pages_arg!r}"
    )
