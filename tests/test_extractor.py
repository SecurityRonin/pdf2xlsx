import pytest
from pathlib import Path
from collections import defaultdict
from pdf2xlsx.extractor import extract_tables
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
