import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable
import pdfplumber
import fitz  # pymupdf
from pdf2xlsx.models import ExtractedTable
from pdf2xlsx.postprocess import postprocess_rows

_YEAR_RE = re.compile(r'^20\d\d$')
_LARGE_NUM_RE = re.compile(r'^[\d,]{4,}$')   # comma-formatted numbers ≥4 digits

_IMG2TABLE_ZOOM = 1.0        # render zoom for img2table; 1.0 avoids 4× memory/time of 2.0
_LINE_MIN_LEN   = 20.0       # pt — minimum h/v line length to count as a table border


def _pages_with_drawn_lines(path: Path, min_len: float = _LINE_MIN_LEN) -> set[int]:
    """
    Return 1-based page numbers that contain horizontal or vertical drawn lines
    (or rectangles) of at least min_len points — a fast proxy for bordered tables.

    Uses pymupdf's vector-path reader; no image rendering required, so this
    runs in <1 s even on 200-page documents.
    """
    pages: set[int] = set()
    doc = fitz.open(str(path))
    for page_num, page in enumerate(doc, start=1):
        for drawing in page.get_drawings():
            for item in drawing.get("items", []):
                kind = item[0]
                if kind == "re":                        # rectangle
                    rect = item[1]
                    if rect.width >= min_len or rect.height >= min_len:
                        pages.add(page_num)
                        break
                elif kind == "l":                       # line segment
                    p1, p2 = item[1], item[2]
                    dx, dy = abs(p2.x - p1.x), abs(p2.y - p1.y)
                    if (dy < 1 and dx >= min_len) or (dx < 1 and dy >= min_len):
                        pages.add(page_num)
                        break
            if page_num in pages:
                break
    doc.close()
    return pages


def _clean_rows(raw: list[list]) -> list[list[str]]:
    return [
        [str(cell).strip() if cell is not None else "" for cell in row]
        for row in raw
    ]


def _is_meaningful_table(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False
    if not rows or max(len(r) for r in rows) < 2:
        return False
    if rows:
        non_empty_header = [c for c in rows[0] if c.strip()]
        if not non_empty_header:
            return False
    return True


def _two_pass_expand(page, finders) -> list[list] | None:
    """
    Re-extract using the bordered tables' column x-positions as explicit vertical
    guides, expanding the search region ±80pt to recover surrounding unbordered rows.
    """
    try:
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


def _extract_pdfplumber(path: Path, on_progress=None) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages, start=1):
            if on_progress:
                on_progress(page_num, total)
            settings = {"text_x_tolerance": 2}
            finders = page.find_tables(table_settings=settings)

            if finders:
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


def _extract_pymupdf(path: Path, **_) -> list[ExtractedTable]:
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


def _extract_camelot_lattice(path: Path, **_) -> list[ExtractedTable]:
    try:
        import camelot  # noqa: PLC0415
        line_pages = _pages_with_drawn_lines(path)
        if not line_pages:
            return []
        pages_str = ",".join(str(p) for p in sorted(line_pages))
        camelot_tables = camelot.read_pdf(
            str(path), pages=pages_str, flavor="lattice", suppress_stdout=True
        )
        tables: list[ExtractedTable] = []
        idx_per_page: dict[int, int] = {}
        for ct in camelot_tables:
            page_num = ct.page
            rows = ct.df.values.tolist()
            cleaned = postprocess_rows(_clean_rows(rows))
            if _is_meaningful_table(cleaned):
                idx = idx_per_page.get(page_num, 0)
                tables.append(ExtractedTable(
                    page=page_num, index=idx, rows=cleaned, source="camelot_lattice"
                ))
                idx_per_page[page_num] = idx + 1
        return _merge_continuation_tables(tables)
    except Exception:
        return []


def _extract_camelot_stream(path: Path, **_) -> list[ExtractedTable]:
    try:
        import camelot  # noqa: PLC0415
        camelot_tables = camelot.read_pdf(
            str(path), pages="all", flavor="stream", suppress_stdout=True
        )
        tables: list[ExtractedTable] = []
        idx_per_page: dict[int, int] = {}
        for ct in camelot_tables:
            page_num = ct.page
            rows = ct.df.values.tolist()
            cleaned = postprocess_rows(_clean_rows(rows))
            if _is_meaningful_table(cleaned):
                idx = idx_per_page.get(page_num, 0)
                tables.append(ExtractedTable(
                    page=page_num, index=idx, rows=cleaned, source="camelot_stream"
                ))
                idx_per_page[page_num] = idx + 1
        return _merge_continuation_tables(tables)
    except Exception:
        return []


def _extract_img2table(path: Path, **_) -> list[ExtractedTable]:
    try:
        from img2table.document import Image as I2TImage  # noqa: PLC0415
        tables: list[ExtractedTable] = []
        doc = fitz.open(str(path))
        for page_num, page in enumerate(doc, start=1):
            try:
                pix = page.get_pixmap(matrix=fitz.Matrix(_IMG2TABLE_ZOOM, _IMG2TABLE_ZOOM), alpha=False)
                img_doc = I2TImage(src=pix.tobytes("png"))
                extracted = img_doc.extract_tables()
                for idx, tbl in enumerate(extracted):
                    try:
                        rows = tbl.df.fillna("").values.tolist()
                    except Exception:
                        rows = [
                            [str(cell.value or "") for cell in cells]
                            for cells in tbl.content.values()
                        ]
                    cleaned = postprocess_rows(_clean_rows(rows))
                    if _is_meaningful_table(cleaned):
                        tables.append(ExtractedTable(
                            page=page_num, index=idx, rows=cleaned, source="img2table"
                        ))
            except Exception:
                continue
        doc.close()
        return _merge_continuation_tables(tables)
    except Exception:
        return []


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


def _score_tables(tables: list[ExtractedTable]) -> float:
    """Score a set of tables for a page: more non-empty cells + more rows = better."""
    if not tables:
        return 0.0
    non_empty = sum(
        1 for t in tables for row in t.rows for cell in row if str(cell).strip()
    )
    row_count = sum(len(t.rows) for t in tables)
    return non_empty + row_count * 0.5


def _select_best_per_page(
    results: dict[str, list[ExtractedTable]],
) -> list[ExtractedTable]:
    """
    For each page, pick the engine whose table set has the highest score
    (most non-empty cells, tie-broken by row count). Each page is decided
    independently so the best engine can differ per page.
    """
    all_pages: set[int] = set()
    for tables in results.values():
        for t in tables:
            all_pages.add(t.page)

    output: list[ExtractedTable] = []
    for page in sorted(all_pages):
        page_results = {
            engine: [t for t in tables if t.page == page]
            for engine, tables in results.items()
            if any(t.page == page for t in tables)
        }
        if not page_results:
            continue

        best_engine = max(page_results, key=lambda e: _score_tables(page_results[e]))
        for idx, t in enumerate(page_results[best_engine]):
            output.append(ExtractedTable(
                page=t.page, index=idx, rows=t.rows, source=t.source,
            ))

    return output


def extract_tables(
    path: Path,
    on_table: Callable[[ExtractedTable], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[ExtractedTable]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    engine_fns: dict[str, Callable] = {
        "pdfplumber":      lambda: _merge_continuation_tables(
                               _extract_pdfplumber(path, on_progress=on_progress)),
        "pymupdf":         lambda: _extract_pymupdf(path),
        "camelot_lattice": lambda: _extract_camelot_lattice(path),
        "camelot_stream":  lambda: _extract_camelot_stream(path),
        "img2table":       lambda: _extract_img2table(path),
    }

    engine_results: dict[str, list[ExtractedTable]] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fn): name for name, fn in engine_fns.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                engine_results[name] = future.result()
            except Exception:
                engine_results[name] = []

    merged = _select_best_per_page(engine_results)
    result = [t for t in merged if not t.is_empty]
    if on_table:
        for t in result:
            on_table(t)
    return result
