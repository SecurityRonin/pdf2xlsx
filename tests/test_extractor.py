import pytest
from pathlib import Path
from collections import defaultdict
from pdf2xlsx.extractor import extract_tables, _merge_continuation_tables
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
