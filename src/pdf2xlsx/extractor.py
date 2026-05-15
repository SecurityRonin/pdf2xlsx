from pathlib import Path
import pdfplumber
import fitz  # pymupdf
from pdf2xlsx.models import ExtractedTable
from pdf2xlsx.postprocess import postprocess_rows


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


def _extract_pdfplumber(path: Path) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_tables = page.extract_tables() or []
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


def extract_tables(path: Path) -> list[ExtractedTable]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    primary = _extract_pdfplumber(path)
    secondary = _extract_pymupdf(path)
    merged = _deduplicate(primary, secondary)
    return [t for t in merged if not t.is_empty]
