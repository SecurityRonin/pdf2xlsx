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
    rows = [["Label", "Val"], ["C", "1"], ["B", "2"], ["A", "3"]]
    result = postprocess_rows(rows)
    labels = [r[0] for r in result]
    assert labels == ["Label", "C", "B", "A"]


def test_header_aligned_to_data_column():
    """Header in col N but data in col N+1 → header shifts into col N+1."""
    rows = [
        ["Label", "High",  "",      "Low",  ""],
        ["Q1",    "",      "$27.40","",     "$15.21"],
        ["Q2",    "",      "$33.32","",     "$25.09"],
    ]
    result = postprocess_rows(rows)
    # 'High' should be in the same column as '$27.40'
    col_of_high = next(
        (c for c, v in enumerate(result[0]) if v == "High"), None
    )
    col_of_2740 = next(
        (c for c, v in enumerate(result[1]) if v == "$27.40"), None
    )
    assert col_of_high is not None, "High header missing"
    assert col_of_2740 is not None, "$27.40 missing"
    assert col_of_high == col_of_2740, (
        f"'High' in col {col_of_high}, '$27.40' in col {col_of_2740} — misaligned"
    )


def test_sparse_same_year_columns_consolidated():
    """
    When rows for the same year have data in different col positions
    (e.g. one row has $ → number in col 3, another has value directly in col 1),
    they should be merged into one column.
    """
    rows = [
        ["",         "",      "2022",       "",     "2023"],
        ["Revenue",  "",      "$1,000",     "",     "$1,200"],   # data in col 2 (after $ merge)
        ["Costs",    "400",   "",           "500",  ""],          # data in col 1
        ["Total",    "",      "$600",       "",     "$700"],
    ]
    result = postprocess_rows(rows)
    # 2022 column: header '2022' + '$1,000' + '400' + '$600' should all be in same column
    # Find which col has '2022'
    year_col = next(
        (c for c, v in enumerate(result[0]) if v == "2022"), None
    )
    assert year_col is not None, "2022 header missing"
    # Revenue '$1,000' should be in the same column
    rev_col = next(
        (c for c, v in enumerate(result[1]) if v == "$1,000"), None
    )
    costs_col = next(
        (c for c, v in enumerate(result[2]) if v == "400"), None
    )
    assert rev_col == year_col, f"Revenue in col {rev_col}, year in col {year_col}"
    assert costs_col == year_col, f"Costs in col {costs_col}, year in col {year_col}"


def test_year_labels_not_merged_into_row_label_column():
    """
    Mirrors the Nutanix p.155 revenue table bug.

    Col 0 has text labels for every data row but is empty in the year row.
    Col 2 has only "2022" (year header). Col 0 and col 2 are mutually exclusive
    so the consolidation previously merged "2022" into col 0, misaligning it
    with the data. After the fix, "2022" must land in the same column as the
    data it labels, NOT in the row-label column.

    Also models the split-column reality: some rows have plain values in col 1,
    others have $-prefixed values in col 3 — all must consolidate to one column.
    """
    # Exact col layout after _attach_currency_prefixes + _drop_empty_columns:
    #   col 0: row labels (empty only in year row)
    #   col 1: plain 2022 data (rows 4,5 only)
    #   col 2: "2022" year label (row 1 only)
    #   col 3: $-prefixed 2022 data (rows 2,3 only)
    #   col 4: plain 2023 data (rows 4,5 only)
    #   col 5: "2023" year label (row 1 only)
    #   col 6: $-prefixed 2023 data (rows 2,3 only)
    rows = [
        ["Fiscal Year Ended", "",        "",      "",            "",        "",      ""],
        ["",                  "",        "2022",  "",            "",        "2023",  ""],
        ["Subscription rev",  "",        "",      "$1,433,773",  "",        "",      "$1,730,848"],
        ["Total revenue",     "",        "",      "$1,580,796",  "",        "",      "$1,862,895"],
        ["Prof services",     "91,744",  "",      "",            "100,852", "",      ""],
        ["Other rev",         "55,279",  "",      "",            "31,188",  "",      ""],
    ]
    result = postprocess_rows(rows)

    # "2022" must NOT be in col 0 (the row-label column)
    year_col = next(
        (c for c, v in enumerate(result[1]) if v == "2022"), None
    )
    assert year_col is not None, "2022 header missing from result"
    assert year_col != 0, (
        f"'2022' landed in col 0 (row-label column) — must be in a data column"
    )

    # All 2022 data must be in the same column as the year label
    sub_col = next(
        (c for c, v in enumerate(result[2]) if v == "$1,433,773"), None
    )
    prof_col = next(
        (c for c, v in enumerate(result[4]) if v == "91,744"), None
    )
    assert sub_col is not None, "$1,433,773 missing"
    assert prof_col is not None, "91,744 missing"
    assert sub_col == year_col, (
        f"$1,433,773 at col {sub_col}, '2022' at col {year_col} — misaligned"
    )
    assert prof_col == year_col, (
        f"91,744 at col {prof_col}, '2022' at col {year_col} — misaligned"
    )


def test_real_nutanix_p149_alignment():
    """Full p.149 simulation: after postprocess, High/Low headers align with values."""
    rows = [
        ["Fiscal 2023", "", "", "", "", "Fiscal 2024", "", "", "", ""],
        ["Fiscal Quarter:", "High", "", "Low", "", "", "High", "", "Low", ""],
        ["First quarter",  "", "$27.40", "", "$15.21", "", "", "$38.92", "", "$29.11"],
        ["Second quarter", "", "$33.32", "", "$25.09", "", "", "$56.94", "", "$36.54"],
    ]
    result = postprocess_rows(rows)
    header_row = result[1]
    q1_row = result[2]
    # Find where High appears in header
    high_col = next((c for c, v in enumerate(header_row) if v == "High"), None)
    val_col = next((c for c, v in enumerate(q1_row) if v == "$27.40"), None)
    assert high_col is not None
    assert val_col is not None
    assert high_col == val_col, f"High at col {high_col}, $27.40 at col {val_col}"


def test_paragraph_rows_dropped():
    """
    Long single-cell prose rows appended by pdfplumber below a multi-column
    table must be removed — they are adjacent paragraphs, not table data.
    """
    rows = [
        ["Option", "Zero Trust", "AD Forests"],
        ["Cost",   "$300K",     "$150K"],
        ["Risk",   "Low",       "High"],
        # paragraph pdfplumber grabbed below the table:
        ["These are not alternatives. Option A is Option B with an AD migration "
         "added on top. A three-forest architecture without Zero Trust is not a "
         "defensible state.", "", ""],
    ]
    result = postprocess_rows(rows)
    for row in result:
        non_empty = [c for c in row if c.strip()]
        assert not (
            len(non_empty) == 1 and len(non_empty[0].split()) > 12
        ), f"Paragraph row survived postprocessing: {non_empty[0][:60]!r}"


def test_short_single_cell_rows_kept():
    """Single-cell rows with short content (section labels) must NOT be dropped."""
    rows = [
        ["Section A"],
        ["Revenue",  "$1,000"],
        ["Costs",    "$800"],
    ]
    result = postprocess_rows(rows)
    assert any("Section A" in c for row in result for c in row), \
        "Short single-cell label row was incorrectly dropped"


def test_multisentence_header_kept():
    """A two-sentence header row must be kept even if it has many words."""
    rows = [
        ["Fiscal Year Ended July 31, 2024. All amounts in thousands.", "2022", "2023"],
        ["Subscription revenue", "$1,433,773", "$1,730,848"],
    ]
    result = postprocess_rows(rows)
    assert result[0][0].startswith("Fiscal Year"), \
        "Multi-word header in row 0 must never be dropped"
