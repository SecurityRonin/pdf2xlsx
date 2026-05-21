import pytest
import time
from pathlib import Path
from collections import defaultdict
from unittest.mock import patch, MagicMock
from pdf2xlsx.extractor import (
    extract_tables, _merge_continuation_tables, _select_best_per_page,
    _IMG2TABLE_ZOOM, _score_tables, _ENGINE_TIMEOUT,
    _clean_rows,
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

def test_camelot_engines_removed():
    """_extract_camelot_lattice and _extract_camelot_stream must not exist.

    Both depend on Ghostscript (hangs on large PDFs); img2table covers bordered
    tables via MuPDF, pdfplumber/pymupdf cover text-based tables.
    """
    import pdf2xlsx.extractor as mod
    assert not hasattr(mod, '_extract_camelot_lattice'), (
        "_extract_camelot_lattice must be removed; img2table covers bordered tables via MuPDF"
    )
    assert not hasattr(mod, '_extract_camelot_stream'), (
        "_extract_camelot_stream must be removed; pdfplumber/pymupdf cover text-based tables"
    )


def test_all_three_engines_called(annual_report):
    """extract_tables must invoke exactly the 3 MuPDF-based engine functions.

    camelot_lattice and camelot_stream are removed: they depend on Ghostscript
    (slow, hangs) while img2table already covers bordered-table detection via MuPDF.
    """
    called = []
    real_pdfplumber = __import__('pdf2xlsx.extractor', fromlist=['_extract_pdfplumber'])._extract_pdfplumber
    real_pymupdf    = __import__('pdf2xlsx.extractor', fromlist=['_extract_pymupdf'])._extract_pymupdf
    real_i2t        = __import__('pdf2xlsx.extractor', fromlist=['_extract_img2table'])._extract_img2table

    def spy(fn, name):
        def wrapper(*a, **kw):
            called.append(name)
            return fn(*a, **kw)
        return wrapper

    with patch('pdf2xlsx.extractor._extract_pdfplumber', spy(real_pdfplumber, 'pdfplumber')), \
         patch('pdf2xlsx.extractor._extract_pymupdf',    spy(real_pymupdf,    'pymupdf')), \
         patch('pdf2xlsx.extractor._extract_img2table',  spy(real_i2t,        'img2table')):
        extract_tables(annual_report)

    assert set(called) == {'pdfplumber', 'pymupdf', 'img2table'}, (
        f"Expected exactly 3 engines called, got: {set(called)}"
    )


def test_engines_run_concurrently(annual_report):
    """All 3 engines must run in parallel: wall time < sum of individual delays."""
    DELAY = 0.15  # seconds per engine
    total_sequential = DELAY * 3  # 0.45s if sequential

    def slow_engine(path, **kw):
        time.sleep(DELAY)
        return []

    with patch('pdf2xlsx.extractor._extract_pdfplumber', slow_engine), \
         patch('pdf2xlsx.extractor._extract_pymupdf',    slow_engine), \
         patch('pdf2xlsx.extractor._extract_img2table',  slow_engine):
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

    with patch('pdf2xlsx.extractor._extract_pymupdf',   boom), \
         patch('pdf2xlsx.extractor._extract_img2table', boom):
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
        and any(c.islower() for c in cell)   # all-CAPS can't be fixed without NLP
        and not cell.startswith('$')
        and not cell.replace(',', '').replace('.', '').replace('-', '').isnumeric()
    ]
    assert stuck == [], (
        f"Found {len(stuck)} cell(s) with words stuck together, e.g. {stuck[0]}"
    )


# ---------------------------------------------------------------------------
# img2table render zoom
# ---------------------------------------------------------------------------

def test_score_penalizes_stuck_word_cells():
    """A table with stuck-word cells must score lower than a clean table with fewer cells."""
    stuck = [ExtractedTable(page=1, index=0, source='bad', rows=[
        ['Header', 'Value'],
        ['DigitalLabsservesasthecompany-widehubforourdigitalinitiative', '1,234'],
        ['AnotherLongStuckWordCellWithNoSpacesAtAllHere', '5,678'],
    ])]
    clean = [ExtractedTable(page=1, index=0, source='good', rows=[
        ['Header', 'Value'],
        ['Digital Labs', '1,234'],
    ])]
    assert _score_tables(stuck) < _score_tables(clean), (
        "A result with stuck-word cells must score lower than a clean result, "
        "so the clean engine wins even with fewer total cells."
    )


def test_select_best_per_page_rejects_stuck_words():
    """_select_best_per_page must not choose an engine whose cells have stuck words."""
    stuck_result = [ExtractedTable(page=2, index=0, source='stream', rows=[
        ['Name', 'Amount'],
        ['DigitalLabsservesasthecompany', '100'],
        ['AnotherStuckWordCell', '200'],
        ['YetAnotherStuckWordCellHere', '300'],
    ])]
    clean_result = [ExtractedTable(page=2, index=0, source='plumber', rows=[
        ['Name', 'Amount'],
        ['Digital Labs', '100'],
    ])]
    result = _select_best_per_page({'stream': stuck_result, 'plumber': clean_result})
    assert len(result) == 1
    assert result[0].source == 'plumber', (
        f"Clean engine must win over stuck-word engine; got source={result[0].source!r}"
    )


def test_select_best_per_page_hard_rejects_stuck_words_when_clean_available():
    """A clean engine with few cells must beat a stuck-word engine with many cells.

    This guards against the -10 soft penalty being overwhelmed by sheer cell
    count when camelot_stream dumps paragraph text as table rows.
    """
    # 50 clean cells + 1 stuck word:
    # with soft penalty: score = 50 + row_bonus - 10 = 40+ → BAD ENGINE WINS
    stuck_rows = [['Name', 'Amount']] + [
        [f'Item{i}', str(i * 100)] for i in range(23)
    ] + [['DigitalLabsservesasthecompanywidehub', '99']]  # 1 stuck-word cell
    stuck_result = [ExtractedTable(page=3, index=0, source='stream', rows=stuck_rows)]

    # 3 clean cells — fewer than stuck engine, but zero stuck words
    clean_result = [ExtractedTable(page=3, index=0, source='plumber', rows=[
        ['Name', 'Amount'],
        ['Digital Labs', '100'],
    ])]

    result = _select_best_per_page({'stream': stuck_result, 'plumber': clean_result})
    assert len(result) == 1
    assert result[0].source == 'plumber', (
        f"Clean engine must win even when stuck engine has more cells; "
        f"got source={result[0].source!r}"
    )


def test_clean_rows_splits_camelcase_stuck_words():
    """_clean_rows must insert spaces in stuck-word cells via camelCase and period junctions.

    On some PDFs, text elements are stored without inter-word spacing; all
    extractors then produce cells like 'IntellectualPropertyandIntangibleAssets'
    or 'million.Restructuringandothercosts'. Splitting at camelCase boundaries
    and punctuation-uppercase boundaries converts these to readable text so they
    no longer match the stuck-word predicate.
    """
    raw = [
        ['Name', 'Amount'],
        ['IntellectualPropertyandIntangibleAssets', '1,000'],   # camelCase
        ['ualPropertyandIntangibleAssets', '2,000'],            # camelCase
        ['million.Restructuringandothercosts', '500'],          # period junction
        ['implementtheinvestmentprocess.Theinvestmentman', '0'],  # period junction
        ['(Amountsinthousandsexceptsharedataandwhereo', 'note'],  # paren junction
    ]
    cleaned = _clean_rows(raw)
    for row_idx in range(1, len(raw)):
        original = raw[row_idx][0]
        cell = cleaned[row_idx][0]
        assert ' ' in cell, (
            f"Stuck word '{original}' must have spaces after cleaning; "
            f"got {cell!r}"
        )


def test_img2table_zoom_is_at_most_one():
    """_IMG2TABLE_ZOOM must be ≤ 1.0 to avoid 4× memory/time overhead."""
    assert _IMG2TABLE_ZOOM <= 1.0, (
        f"_IMG2TABLE_ZOOM={_IMG2TABLE_ZOOM}; must be ≤1.0 (was 2.0, causing 4× slowdown)"
    )


def test_on_table_called_before_slow_engines_finish(annual_report):
    """on_table must fire as soon as the first engine has results, not after all finish."""
    SLOW = 1.5
    fast_result = [ExtractedTable(page=1, index=0, rows=[["H","V"],["a","1"]], source="fast")]

    first_call_time = []
    def fast_engine(path, **kw): return fast_result
    def slow_engine(path, **kw): time.sleep(SLOW); return []

    t0 = time.monotonic()
    with patch('pdf2xlsx.extractor._extract_pdfplumber', fast_engine), \
         patch('pdf2xlsx.extractor._extract_pymupdf',    slow_engine), \
         patch('pdf2xlsx.extractor._extract_img2table',  slow_engine):
        extract_tables(annual_report, on_table=lambda t: first_call_time.append(time.monotonic()))

    assert first_call_time, "on_table must be called at least once"
    elapsed = first_call_time[0] - t0
    assert elapsed < SLOW * 0.8, (
        f"on_table must fire before slow engines finish; "
        f"first call at {elapsed:.2f}s, slow engines take {SLOW}s"
    )


def test_on_table_called_again_when_better_result_arrives(annual_report):
    """on_table must be called a second time for a page when a later engine beats the first."""
    sparse = [ExtractedTable(page=1, index=0, rows=[["H","V"],["",""]],         source="sparse")]
    dense  = [ExtractedTable(page=1, index=0, rows=[["H","V"],["a","1"],["b","2"],["c","3"]], source="dense")]

    calls = []
    def sparse_engine(path, **kw): return sparse
    def dense_engine(path, **kw):  time.sleep(0.05); return dense
    def empty_engine(path, **kw):  return []

    with patch('pdf2xlsx.extractor._extract_pdfplumber', sparse_engine), \
         patch('pdf2xlsx.extractor._extract_pymupdf',    dense_engine), \
         patch('pdf2xlsx.extractor._extract_img2table',  empty_engine):
        extract_tables(annual_report, on_table=calls.append)

    page1 = [t for t in calls if t.page == 1]
    assert len(page1) >= 2, (
        f"on_table must fire at least twice for page 1 (initial + improvement); got {len(page1)}"
    )
    assert any(t.source == "dense" for t in page1), (
        f"Dense engine result must appear in on_table calls; sources seen: {[t.source for t in page1]}"
    )


def test_engine_timeout_does_not_block(annual_report):
    """extract_tables must return even if one engine hangs indefinitely."""
    import threading
    import pdf2xlsx.extractor as extractor_mod

    hang_event = threading.Event()

    def hanging_engine(path, **kw):
        hang_event.wait()  # blocks forever until event is set

    fast_result = [ExtractedTable(page=1, index=0, rows=[["H", "V"], ["a", "1"]], source="fast")]

    def fast_engine(path, **kw):
        return fast_result

    SHORT_TIMEOUT = 3  # seconds — enough to prove timeout works without slowing suite
    margin = 5
    deadline = SHORT_TIMEOUT + margin

    t0 = time.monotonic()
    with patch.object(extractor_mod, '_ENGINE_TIMEOUT', SHORT_TIMEOUT), \
         patch('pdf2xlsx.extractor._extract_pdfplumber', fast_engine), \
         patch('pdf2xlsx.extractor._extract_pymupdf',    fast_engine), \
         patch('pdf2xlsx.extractor._extract_img2table',  hanging_engine):
        tables = extract_tables(annual_report)
    elapsed = time.monotonic() - t0
    hang_event.set()  # release stuck thread so it can exit cleanly

    assert elapsed < deadline, (
        f"extract_tables must complete within {deadline}s when one engine hangs; "
        f"took {elapsed:.1f}s (short_timeout={SHORT_TIMEOUT}s, margin={margin}s)"
    )
    assert isinstance(tables, list), "Must still return a list when an engine times out"


