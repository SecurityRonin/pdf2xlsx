"""Tests for table post-processing: currency merge + empty column removal."""
from pdf2xlsx.postprocess import postprocess_rows


def test_dollar_immediately_before_number():
    rows = [["Item", "$", "100"]]
    result = postprocess_rows(rows)
    assert result == [["Item", "$100"]]


def test_dollar_with_empty_between_and_number():
    # $ in col 1, empty col 2, number in col 3 — still merge
    rows = [["Item", "$", "", "1,234.56"]]
    result = postprocess_rows(rows)
    # $ should attach to the nearest number
    assert any("$1,234.56" in cell for row in result for cell in row)


def test_dollar_column_across_rows_merged():
    # Simulates the Nutanix stock price table structure
    rows = [
        ["Fiscal Quarter:", "High", "", "Low"],
        ["First quarter",   "$",    "27.40", ""],
        ["Second quarter",  "$",    "33.32", ""],
    ]
    result = postprocess_rows(rows)
    # $ should be merged with 27.40 and 33.32
    assert any("$27.40" in cell for cell in result[1])
    assert any("$33.32" in cell for cell in result[2])


def test_empty_columns_dropped():
    rows = [
        ["Name", "", "Value"],
        ["Alice", "", "100"],
        ["Bob", "", "200"],
    ]
    result = postprocess_rows(rows)
    # Middle empty column should be dropped
    assert all(len(row) == 2 for row in result)
    assert result[0] == ["Name", "Value"]


def test_partially_empty_column_kept():
    # Column with at least one non-empty cell should be kept
    rows = [
        ["A", "B", "C"],
        ["1", "",  "3"],
        ["4", "5", "6"],
    ]
    result = postprocess_rows(rows)
    assert len(result[0]) == 3


def test_multiple_currency_columns():
    rows = [
        ["Q1", "$", "100", "$", "200"],
        ["Q2", "$", "150", "$", "250"],
    ]
    result = postprocess_rows(rows)
    assert any("$100" in cell for cell in result[0])
    assert any("$200" in cell for cell in result[0])
    assert any("$150" in cell for cell in result[1])
    assert any("$250" in cell for cell in result[1])


def test_non_currency_cells_unchanged():
    rows = [["Name", "Score"], ["Alice", "A+"]]
    result = postprocess_rows(rows)
    assert result[0][0] == "Name"
    assert result[1][1] == "A+"


def test_empty_rows_removed():
    rows = [
        ["Header", "Value"],
        ["", ""],
        ["Data", "100"],
    ]
    result = postprocess_rows(rows)
    assert len(result) == 2
    assert result[0] == ["Header", "Value"]
    assert result[1] == ["Data", "100"]


def test_real_nutanix_stock_table():
    """Simulates Nutanix p.149 — 16-col mess → clean 5-col table."""
    rows = [
        ["Fiscal 2023"] + [""] * 15,
        ["Fiscal Quarter:", "", "High", "", "", "Low", "", "", "", "", "High", "", "", "Low", "", ""],
        ["First quarter",  "", "$", "27.40", "", "", "$", "15.21", "", "", "$", "38.92", "", "", "$", "29.11"],
        ["Second quarter", "$", "", "33.32", "$", "", "", "25.09", "", "$", "",  "56.94", "$", "", "",  "36.54"],
    ]
    result = postprocess_rows(rows)
    # Should have far fewer columns than 16
    max_cols = max(len(r) for r in result)
    assert max_cols < 12, f"Expected <12 cols after postprocessing, got {max_cols}"
    # Values should be present with $ prefix
    all_cells = [cell for row in result for cell in row]
    assert any("$27.40" in c for c in all_cells)
    assert any("$33.32" in c for c in all_cells)
    assert any("$15.21" in c for c in all_cells)


def test_preserves_row_order():
    rows = [["C"], ["B"], ["A"]]
    # Pad to avoid single-col filter in extractor — postprocess gets lists
    rows = [["Label", "Val"], ["C", "1"], ["B", "2"], ["A", "3"]]
    result = postprocess_rows(rows)
    labels = [r[0] for r in result]
    assert labels == ["Label", "C", "B", "A"]
