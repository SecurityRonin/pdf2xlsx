import re
from pathlib import Path
from typing import Callable
import pdfplumber
import fitz  # pymupdf
from pdf2xlsx.models import ExtractedTable
from pdf2xlsx.postprocess import postprocess_rows

_YEAR_RE = re.compile(r'^20\d\d$')
_LARGE_NUM_RE = re.compile(r'^[\d,]{4,}$')   # comma-formatted numbers ≥4 digits


def _clean_rows(raw: list[list]) -> list[list[str]]:
    return [
        [str(cell).strip() if cell is not None else "" for cell in row]
        for row in raw
    ]


def _is_meaningful_table(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False
    # Need at least 2 columns
    if not rows or max(len(r) for r in rows) < 2:
        return False
    # Header row must not be entirely empty
    if rows:
        non_empty_header = [c for c in rows[0] if c.strip()]
        if not non_empty_header:
            return False
    return True


def _two_pass_expand(page, finders) -> list[list] | None:
    """
    Re-extract using the bordered tables' column x-positions as explicit vertical
    guides, expanding the search region ±80pt to recover surrounding unbordered rows.

    Returns raw rows if the result has more rows than the bordered tables alone,
    otherwise None (fall back to line-based output).
    """
    try:
        # Derive column boundary x-positions from all detected cell bboxes
        xs: set[float] = set()
        for tf in finders:
            for (x0, _y0, x1, _y1) in tf.cells:
                xs.add(round(x0, 1))
                xs.add(round(x1, 1))
        v_lines = sorted(xs)
        if len(v_lines) < 2:
            return None

        min_x = min(tf.bbox[0] for tf in finders)
        max_x = max(tf.bbox[2] for tf in finders)
        min_y = max(0, min(tf.bbox[1] for tf in finders) - 80)
        max_y = min(page.height, max(tf.bbox[3] for tf in finders) + 80)

        cropped = page.crop((min_x, min_y, max_x, max_y))
        extended = cropped.extract_table(table_settings={
            "vertical_strategy": "explicit",
            "horizontal_strategy": "text",
            "explicit_vertical_lines": v_lines,
            "text_y_tolerance": 5,
            "snap_x_tolerance": 5,
        })

        bordered_total = sum(len(tf.extract()) for tf in finders)
        if extended and len(extended) > bordered_total:
            return extended
    except Exception:
        pass
    return None


def _extract_pdfplumber(path: Path) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # text_x_tolerance=2 detects word spaces as narrow as 2 pts.
            # Some PDFs (e.g. TimesNewRoman at small sizes) encode word gaps
            # of ~2.7 pts which pdfplumber's default of 3 pts misses entirely.
            settings = {"text_x_tolerance": 2}
            finders = page.find_tables(table_settings=settings)

            if finders:
                # Try two-pass: use bordered column structure to recover unbordered rows
                extended = _two_pass_expand(page, finders)
                if extended:
                    page_tables = [extended]
                else:
                    page_tables = [tf.extract() for tf in finders]
            else:
                page_tables = []

            idx = 0
            for raw_table in page_tables:
                if not raw_table:
                    continue
                cleaned = postprocess_rows(_clean_rows(raw_table))
                if _is_meaningful_table(cleaned):
                    tables.append(ExtractedTable(
                        page=page_num,
                        index=idx,
                        rows=cleaned,
                        source="pdfplumber",
                    ))
                    idx += 1
    return tables


def _extract_pymupdf(path: Path) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    doc = fitz.open(str(path))
    for page_num, page in enumerate(doc, start=1):
        try:
            found = page.find_tables()
        except Exception:
            continue
        idx = 0
        for table in found.tables:
            rows = table.extract()
            if not rows:
                continue
            cleaned = postprocess_rows(_clean_rows(rows))
            if _is_meaningful_table(cleaned):
                tables.append(ExtractedTable(
                    page=page_num,
                    index=idx,
                    rows=cleaned,
                    source="pymupdf",
                ))
                idx += 1
    doc.close()
    return tables


def _row_is_data(row: list[str]) -> bool:
    """True when a row contains financial data (year or large number) — not a header."""
    cells = [c.strip() for c in row if c.strip()]
    return any(
        _YEAR_RE.match(c) or _LARGE_NUM_RE.match(c.replace(',', ''))
        for c in cells
    )


def _merge_continuation_tables(tables: list[ExtractedTable]) -> list[ExtractedTable]:
    """
    Merge consecutive same-page sub-tables that pdfplumber splits at row-group
    boundaries (e.g. one sub-table per executive in a compensation table).

    Two consecutive tables are merged when:
    - Same page and same source
    - Same column count
    - The second table's first row is a data row (contains a year or large number),
      not an all-text column-header row indicating a genuinely new table.
    """
    if not tables:
        return tables
    result: list[ExtractedTable] = []
    i = 0
    while i < len(tables):
        current = tables[i]
        while i + 1 < len(tables):
            nxt = tables[i + 1]
            if nxt.page != current.page or nxt.source != current.source:
                break
            cur_cols = max((len(r) for r in current.rows), default=0)
            nxt_cols = max((len(r) for r in nxt.rows), default=0)
            if cur_cols != nxt_cols:
                break
            if not nxt.rows or not _row_is_data(nxt.rows[0]):
                break
            current = ExtractedTable(
                page=current.page,
                index=current.index,
                rows=current.rows + nxt.rows,
                source=current.source,
            )
            i += 1
        result.append(current)
        i += 1
    return result


def _deduplicate(
    primary: list[ExtractedTable],
    secondary: list[ExtractedTable],
) -> list[ExtractedTable]:
    """Use primary results; supplement with secondary on pages primary missed."""
    primary_pages = {t.page for t in primary}
    extras = [t for t in secondary if t.page not in primary_pages]
    # Re-index extras so indices are sequential from 0
    result = list(primary)
    for t in extras:
        result.append(t)
    return result


def extract_tables(
    path: Path,
    on_table: Callable[[ExtractedTable], None] | None = None,
) -> list[ExtractedTable]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    primary = _merge_continuation_tables(_extract_pdfplumber(path))
    secondary = _merge_continuation_tables(_extract_pymupdf(path))
    merged = _deduplicate(primary, secondary)
    result = [t for t in merged if not t.is_empty]
    if on_table:
        for t in result:
            on_table(t)
    return result
