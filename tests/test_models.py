from pdf2xlsx.models import ExtractedTable


def test_table_has_required_fields():
    table = ExtractedTable(
        page=1, index=0,
        rows=[["Name", "Value"], ["Apple", "100"]],
        source="pdfplumber",
    )
    assert table.page == 1
    assert table.index == 0
    assert len(table.rows) == 2
    assert table.source == "pdfplumber"


def test_table_sheet_name_truncated_to_31_chars():
    table = ExtractedTable(page=99, index=0, rows=[], source="pdfplumber")
    assert len(table.sheet_name) <= 31


def test_table_sheet_name_format():
    table = ExtractedTable(page=3, index=1, rows=[], source="pdfplumber")
    assert table.sheet_name == "Table 2 (p.3)"


def test_table_row_and_col_count():
    table = ExtractedTable(
        page=1, index=0,
        rows=[["A", "B"], ["1", "2"], ["3", "4"]],
        source="pymupdf",
    )
    assert table.row_count == 3
    assert table.col_count == 2


def test_empty_table_is_skippable():
    table = ExtractedTable(page=1, index=0, rows=[], source="pdfplumber")
    assert table.is_empty


def test_single_row_table_is_skippable():
    table = ExtractedTable(page=1, index=0, rows=[["Header only"]], source="pdfplumber")
    assert table.is_empty


def test_two_row_table_is_not_empty():
    table = ExtractedTable(page=1, index=0, rows=[["H"], ["V"]], source="pdfplumber")
    assert not table.is_empty
