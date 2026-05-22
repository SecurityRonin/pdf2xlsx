import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable
import pdfplumber
import fitz  # pymupdf
from pdf2xlsx.models import ExtractedTable
from pdf2xlsx.postprocess import postprocess_rows
from pdf2xlsx.engines.tabletransformer import _extract_tabletransformer

_YEAR_RE = re.compile(r'^20\d\d$')
_LARGE_NUM_RE = re.compile(r'^[\d,]{4,}$')   # comma-formatted numbers ≥4 digits
_STUCK_SPLIT_RE = re.compile(r'([a-z.,;:()])([A-Z])')  # split at camelCase or punct+uppercase

_IMG2TABLE_ZOOM  = 1.0   # render zoom for img2table; 1.0 avoids 4× memory/time of 2.0
_ENGINE_TIMEOUT  = 120   # seconds — thread-level safety net for all engines

# Quality scorer constants
_NUMERIC_CELL_RE = re.compile(
    r'^[\$\(]?[\d,\.]{3,}[\)%]?$|^[—\-\–]$|^20[0-9]{2}$'
)
_PARTIAL_NUM_RE = re.compile(r'\d,\d{1,2}$')   # truncated comma-number e.g. "$15,8"
_COL_OCC_THRESHOLD        = 0.30
_COL_FRAG_THRESHOLD       = 0.30
_TYPE_CONSISTENCY_MIN     = 0.60  # max(text_ratio, numeric_ratio) must exceed this


def _clean_rows(raw: list[list]) -> list[list[str]]:
    rows = []
    for row in raw:
        cleaned = []
        for cell in row:
            s = str(cell).strip() if cell is not None else ""
            # For stuck-word cells, insert spaces at camelCase boundaries.
            # _is_stuck_word is defined later in this module but resolved at
            # call time, not definition time — safe to reference here.
            if _is_stuck_word(s):
                s = _STUCK_SPLIT_RE.sub(r'\1 \2', s)
            cleaned.append(s)
        rows.append(cleaned)
    return rows


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


def _is_stuck_word(cell: str) -> bool:
    """True when a cell looks like mixed-case words concatenated without spaces.

    All-uppercase strings (e.g. 'NOTESTOCONSOLIDATEDFINANCIALST') are excluded:
    they cannot be split without word-segmentation NLP and may be legitimate
    acronyms or abbreviation strings.
    """
    s = cell.strip()
    return (
        len(s) > 20
        and ' ' not in s
        and any(c.isupper() for c in s[1:])
        and any(c.islower() for c in s)      # must be mixed case, not all-caps
        and not s.startswith('$')
        and not s.replace(',', '').replace('.', '').replace('-', '').isnumeric()
    )


def _cell_quality(s: str) -> str:
    """Classify a non-empty cell as 'fragment', 'numeric', or 'text'.

    Only _PARTIAL_NUM_RE (a cell ending mid-comma-number like "$15,8") triggers
    'fragment'.  Short integers like "1", "2", "29" are valid data and classified
    as 'text' so they don't unfairly penalise single-digit data columns.
    """
    if _PARTIAL_NUM_RE.search(s):
        return 'fragment'
    if _NUMERIC_CELL_RE.match(s):
        return 'numeric'
    return 'text'


def _score_single_table(t: ExtractedTable) -> float:
    """
    Quality-first score: non_empty_cells × (good_col_ratio)²

    A "good" column satisfies all three:
      - occupancy        ≥ _COL_OCC_THRESHOLD     (column isn't mostly empty)
      - frag+stuck ratio ≤ _COL_FRAG_THRESHOLD    (values are whole, not split)
      - type_consistency ≥ _TYPE_CONSISTENCY_MIN  (column is predominantly one type)

    Type consistency rejects columns that mix label text and financial numbers —
    that pattern indicates rows from different logical tables got merged.
    Squaring good_col_ratio amplifies structural badness non-linearly.
    """
    rows = t.rows
    if not rows:
        return 0.0
    n_cols = max((len(r) for r in rows), default=0)
    n_rows = len(rows)
    if n_cols == 0:
        return 0.0
    padded = [list(r) + [''] * (n_cols - len(r)) for r in rows]
    non_empty_total = 0
    good_cols = 0
    for c in range(n_cols):
        col = [str(padded[r][c]).strip() for r in range(n_rows)]
        non_empty = [x for x in col if x]
        non_empty_total += len(non_empty)
        if not non_empty:
            continue
        occupancy = len(non_empty) / n_rows
        if occupancy < _COL_OCC_THRESHOLD:
            continue
        qualities = [_cell_quality(x) for x in non_empty]
        frag_ratio = qualities.count('fragment') / len(qualities)
        stuck_ratio = sum(1 for x in non_empty if _is_stuck_word(x)) / len(non_empty)
        if frag_ratio + stuck_ratio * 2 > _COL_FRAG_THRESHOLD:
            continue
        # Type consistency: only meaningful with ≥3 cells (2-row tables have just
        # 1 header + 1 datum, which always looks 50/50 and would be wrongly penalised).
        if len(non_empty) >= 3:
            text_ratio = qualities.count('text') / len(qualities)
            num_ratio  = qualities.count('numeric') / len(qualities)
            if max(text_ratio, num_ratio) < _TYPE_CONSISTENCY_MIN:
                continue
        good_cols += 1
    if non_empty_total == 0:
        return 0.0
    good_col_ratio = good_cols / n_cols
    return non_empty_total * good_col_ratio ** 2


def _score_tables(tables: list[ExtractedTable]) -> float:
    if not tables:
        return 0.0
    return sum(_score_single_table(t) for t in tables)


def _has_stuck_words(tables: list[ExtractedTable]) -> bool:
    return any(
        _is_stuck_word(cell)
        for t in tables
        for row in t.rows
        for cell in row
    )


def _select_best_per_page(
    results: dict[str, list[ExtractedTable]],
) -> list[ExtractedTable]:
    """
    For each page, pick the engine whose table set has the highest score.

    Two-tier selection:
    1. Hard-reject engines with any stuck-word cells (concatenated words = bad parse).
    2. Among surviving engines, pick the one with the highest _score_tables.
    Fall back to the full candidate set only when every engine produces stuck words.
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

        clean = {e: tbls for e, tbls in page_results.items() if not _has_stuck_words(tbls)}
        candidates = clean if clean else page_results

        best_engine = max(candidates, key=lambda e: _score_tables(candidates[e]))
        for idx, t in enumerate(candidates[best_engine]):
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
        "pdfplumber":       lambda: _merge_continuation_tables(
                                _extract_pdfplumber(path, on_progress=on_progress)),
        "pymupdf":          lambda: _extract_pymupdf(path),
        "img2table":        lambda: _extract_img2table(path),
        "tabletransformer": lambda: _extract_tabletransformer(path),
    }

    # page -> (best_score, tables) seen so far across completed engines
    page_best: dict[int, tuple[float, list[ExtractedTable]]] = {}

    def emit_improvements(tables: list[ExtractedTable]) -> None:
        """Emit on_table for any page where these tables beat the current best."""
        if not on_table:
            return
        by_page: dict[int, list[ExtractedTable]] = {}
        for t in tables:
            by_page.setdefault(t.page, []).append(t)
        for page in sorted(by_page):
            page_tables = by_page[page]
            score = _score_tables(page_tables)
            if score > page_best.get(page, (0.0,))[0]:
                page_best[page] = (score, page_tables)
                for t in page_tables:
                    on_table(t)

    engine_results: dict[str, list[ExtractedTable]] = {}
    executor = ThreadPoolExecutor(max_workers=4)
    futures = {executor.submit(fn): name for name, fn in engine_fns.items()}
    try:
        for future in as_completed(futures, timeout=_ENGINE_TIMEOUT):
            name = futures[future]
            try:
                result_tables = future.result()
            except Exception:
                result_tables = []
            engine_results[name] = result_tables
            emit_improvements(result_tables)   # <-- progressive emission
    except TimeoutError:
        # One or more engines exceeded the per-call budget; treat them as empty.
        for fut, name in futures.items():
            engine_results.setdefault(name, [])
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # Final authoritative selection (consistent with what was progressively emitted)
    merged = _select_best_per_page(engine_results)
    return [t for t in merged if not t.is_empty]
