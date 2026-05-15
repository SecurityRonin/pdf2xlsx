import re

_CURRENCY_RE = re.compile(r'^[$£€¥₹()\-]+$')
_NUMBER_RE = re.compile(r'^[\d,.\-]+$')


def _attach_currency_prefixes(rows: list[list[str]]) -> list[list[str]]:
    """In each row, attach lone currency-symbol cells to the nearest following numeric cell."""
    result = []
    for row in rows:
        new_row = list(row)
        for i, cell in enumerate(new_row):
            stripped = cell.strip()
            if stripped and _CURRENCY_RE.match(stripped):
                # Walk forward to find the next non-empty cell
                for j in range(i + 1, len(new_row)):
                    candidate = new_row[j].strip()
                    if candidate:
                        # Only merge if the target looks numeric
                        if _NUMBER_RE.match(candidate.replace(',', '').replace('.', '').lstrip('-')):
                            new_row[j] = stripped + candidate
                            new_row[i] = ''
                        break
        result.append(new_row)
    return result


def _drop_empty_columns(rows: list[list[str]]) -> list[list[str]]:
    """Remove columns that are empty (whitespace-only) in every row."""
    if not rows:
        return rows
    num_cols = max(len(r) for r in rows)
    padded = [r + [''] * (num_cols - len(r)) for r in rows]
    keep = [
        col for col in range(num_cols)
        if any(padded[row_idx][col].strip() for row_idx in range(len(padded)))
    ]
    if not keep:
        return rows
    return [[row[col] for col in keep] for row in padded]


def _drop_empty_rows(rows: list[list[str]]) -> list[list[str]]:
    """Remove rows where every cell is empty or whitespace."""
    return [row for row in rows if any(cell.strip() for cell in row)]


def _detect_header_zone(rows: list[list[str]], max_header: int = 3) -> int:
    """Count leading rows that contain no numeric/currency data values."""
    for i, row in enumerate(rows[:max_header]):
        non_empty = [c.strip() for c in row if c.strip()]
        numeric = [
            c for c in non_empty
            if _NUMBER_RE.match(c.lstrip('$£€¥').replace(',', '').lstrip('-'))
        ]
        if numeric:
            return max(1, i)
    return min(max_header, max(1, len(rows) - 1))


def _align_header_to_data_columns(rows: list[list[str]]) -> list[list[str]]:
    """
    Fix the column-offset that arises when a currency symbol was stripped out:
    if column N has content only in the top rows (header zone) and column N+1
    has content only in the bottom rows (data zone), move col N's header into
    col N+1 so headers and their data share the same column index.
    """
    if len(rows) < 2:
        return rows

    header_zone = _detect_header_zone(rows)
    num_cols = max(len(r) for r in rows)
    padded = [list(r) + [''] * (num_cols - len(r)) for r in rows]

    changed = True
    while changed:
        changed = False
        nc = max(len(r) for r in padded)
        for col in range(nc - 1):
            in_header = [padded[r][col].strip() for r in range(header_zone)]
            in_data = [padded[r][col].strip() for r in range(header_zone, len(padded))]
            nxt_header = [padded[r][col + 1].strip() for r in range(header_zone)]
            nxt_data = [padded[r][col + 1].strip() for r in range(header_zone, len(padded))]

            col_header_only = any(in_header) and not any(in_data)
            nxt_data_only = not any(nxt_header) and any(nxt_data)

            if col_header_only and nxt_data_only:
                for r in range(header_zone):
                    if padded[r][col].strip():
                        padded[r][col + 1] = padded[r][col]
                        padded[r][col] = ''
                changed = True
                break  # restart scan after any change

    return padded


def _consolidate_sparse_columns(
    rows: list[list[str]],
    window: int = 2,
) -> list[list[str]]:
    """
    Merge pairs of nearby columns that carry mutually-exclusive data into one.

    Handles the case where different rows for the same logical column land in
    different physical columns (e.g. rows with a $ prefix get shifted right by
    one after currency attachment, leaving their values one column over from
    rows without a $ prefix).

    Only merges if:
    - The two columns never both have content in the same row (mutually exclusive)
    - They are within `window` positions of each other
    - They don't both have non-empty header content (which would indicate they
      are genuinely different labeled columns like '2022' vs '2023')
    """
    if not rows:
        return rows

    header_zone = _detect_header_zone(rows)
    num_rows = len(rows)
    padded = [list(r) + [''] * (max(len(r2) for r2 in rows) - len(r)) for r in rows]

    changed = True
    while changed:
        changed = False
        nc = max(len(r) for r in padded)
        for col_a in range(nc):
            for col_b in range(col_a + 1, min(col_a + 1 + window, nc)):
                vals_a = [padded[r][col_a].strip() for r in range(num_rows)]
                vals_b = [padded[r][col_b].strip() for r in range(num_rows)]

                # Skip if both cols have header content (different labeled columns)
                hdr_a = any(vals_a[r] for r in range(header_zone))
                hdr_b = any(vals_b[r] for r in range(header_zone))
                if hdr_a and hdr_b:
                    continue

                # Skip merging INTO col_a if it already has content in both
                # header and data zones — it's a persistent row-label column
                # and absorbing sparse year/data from col_b would misalign it.
                data_a = any(vals_a[r] for r in range(header_zone, num_rows))
                if hdr_a and data_a:
                    continue

                # Skip if they conflict (both non-empty in the same row)
                if any(vals_a[r] and vals_b[r] for r in range(num_rows)):
                    continue

                # Skip if col_b has nothing to contribute
                if not any(vals_b):
                    continue

                # Merge col_b into col_a
                for r in range(num_rows):
                    if vals_b[r]:
                        padded[r][col_a] = vals_b[r]
                        padded[r][col_b] = ''
                changed = True
                break
            if changed:
                break

    return padded


def postprocess_rows(rows: list[list[str]]) -> list[list[str]]:
    """Clean up raw pdfplumber/pymupdf extraction artefacts."""
    rows = _attach_currency_prefixes(rows)
    rows = _drop_empty_columns(rows)
    rows = _align_header_to_data_columns(rows)
    rows = _consolidate_sparse_columns(rows)
    rows = _drop_empty_columns(rows)
    rows = _drop_empty_rows(rows)
    return rows
