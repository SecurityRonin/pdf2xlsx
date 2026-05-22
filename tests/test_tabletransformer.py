"""
RED tests for the Table Transformer ONNX engine.

All tests here define the contract; none should pass until the implementation
in src/pdf2xlsx/engines/tabletransformer.py is written.
"""
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 1. Graceful fallback when ONNX model files are absent
# ---------------------------------------------------------------------------

def test_returns_empty_when_models_missing(tmp_path):
    """Engine must return [] (not raise) when ONNX files are not in the cache."""
    from pdf2xlsx.engines.tabletransformer import _extract_tabletransformer
    with patch("pdf2xlsx.engines.tabletransformer.MODEL_CACHE_DIR", tmp_path):
        result = _extract_tabletransformer(Path("nonexistent.pdf"))
    assert result == []


def test_returns_empty_when_onnxruntime_unavailable(tmp_path, monkeypatch):
    """Engine must return [] gracefully if onnxruntime is not installed."""
    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", None)
    from pdf2xlsx.engines import tabletransformer as mod
    # Force re-evaluation with missing onnxruntime by calling directly
    with patch("pdf2xlsx.engines.tabletransformer.MODEL_CACHE_DIR", tmp_path):
        # Create fake model files so the missing-files guard doesn't fire first
        (tmp_path / "detect.onnx").write_bytes(b"fake")
        (tmp_path / "structure.onnx").write_bytes(b"fake")
        result = mod._extract_tabletransformer(Path("nonexistent.pdf"))
    assert result == []


# ---------------------------------------------------------------------------
# 2. Image preprocessing
# ---------------------------------------------------------------------------

def test_preprocess_image_shape_and_dtype():
    """_preprocess_image must return float32 tensor with shape [1, 3, H, W]."""
    from PIL import Image
    from pdf2xlsx.engines.tabletransformer import _preprocess_image
    img = Image.new("RGB", (320, 240), color=(128, 64, 32))
    tensor, (h, w) = _preprocess_image(img, target_size=800)
    assert tensor.dtype == np.float32
    assert tensor.ndim == 4
    assert tensor.shape[0] == 1   # batch
    assert tensor.shape[1] == 3   # channels


def test_preprocess_image_resizes_to_target_size():
    """Largest side of resized image must equal target_size."""
    from PIL import Image
    from pdf2xlsx.engines.tabletransformer import _preprocess_image
    # Landscape: 1600×900
    img = Image.new("RGB", (1600, 900))
    _, (h, w) = _preprocess_image(img, target_size=800)
    assert max(h, w) == 800


def test_preprocess_image_normalizes_with_imagenet_stats():
    """A pure-white image must be normalized to (1.0 - mean) / std per channel."""
    from PIL import Image
    from pdf2xlsx.engines.tabletransformer import _preprocess_image, _IMAGENET_MEAN, _IMAGENET_STD
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    tensor, _ = _preprocess_image(img, target_size=200)
    # All pixels should be (1.0 - mean) / std
    expected = (1.0 - _IMAGENET_MEAN) / _IMAGENET_STD
    for c in range(3):
        np.testing.assert_allclose(tensor[0, c, 0, 0], expected[c], atol=1e-5)


# ---------------------------------------------------------------------------
# 3. Table detection post-processing
# ---------------------------------------------------------------------------

def _make_detect_session(logits, pred_boxes):
    """Return a mocked ORT session whose run() returns (logits, pred_boxes)."""
    sess = MagicMock()
    sess.run.return_value = [logits, pred_boxes]
    return sess


def test_detect_tables_keeps_high_confidence_table():
    """A query with table class probability > threshold must produce a bbox."""
    from pdf2xlsx.engines.tabletransformer import _detect_tables
    # 1 query: class 0 (table) wins with high logit
    logits    = np.array([[[10.0, -5.0, -5.0]]], dtype=np.float32)  # [1,1,3]
    pred_boxes = np.array([[[0.5, 0.5, 0.4, 0.3]]], dtype=np.float32)  # [1,1,4] cx,cy,w,h
    sess = _make_detect_session(logits, pred_boxes)
    result = _detect_tables(sess, np.zeros((1, 3, 100, 80), dtype=np.float32), (100, 80))
    assert len(result) == 1


def test_detect_tables_drops_low_confidence_query():
    """A query dominated by the background class must be filtered out."""
    from pdf2xlsx.engines.tabletransformer import _detect_tables
    # class 2 (no-object/background) wins
    logits    = np.array([[[-5.0, -5.0, 10.0]]], dtype=np.float32)
    pred_boxes = np.array([[[0.5, 0.5, 0.4, 0.3]]], dtype=np.float32)
    sess = _make_detect_session(logits, pred_boxes)
    result = _detect_tables(sess, np.zeros((1, 3, 100, 80), dtype=np.float32), (100, 80))
    assert len(result) == 0


def test_detect_tables_converts_boxes_to_xyxy():
    """Output bounding boxes must be in (x1, y1, x2, y2) image-pixel format."""
    from pdf2xlsx.engines.tabletransformer import _detect_tables
    # cx=0.5, cy=0.5, w=0.4, h=0.3 in a 100×80 image
    # x1 = (0.5-0.2)*100=30, y1=(0.5-0.15)*80=28, x2=(0.5+0.2)*100=70, y2=(0.5+0.15)*80=52
    logits    = np.array([[[10.0, -5.0, -5.0]]], dtype=np.float32)
    pred_boxes = np.array([[[0.5, 0.5, 0.4, 0.3]]], dtype=np.float32)
    sess = _make_detect_session(logits, pred_boxes)
    (x1, y1, x2, y2), = _detect_tables(sess, np.zeros((1, 3, 80, 100), dtype=np.float32), (80, 100))
    assert pytest.approx(x1, abs=0.5) == 30.0
    assert pytest.approx(y1, abs=0.5) == 28.0
    assert pytest.approx(x2, abs=0.5) == 70.0
    assert pytest.approx(y2, abs=0.5) == 52.0


# ---------------------------------------------------------------------------
# 4. Structure recognition post-processing
# ---------------------------------------------------------------------------

def _make_struct_session(logits, pred_boxes):
    sess = MagicMock()
    sess.run.return_value = [logits, pred_boxes]
    return sess


def test_recognize_structure_separates_rows_and_columns():
    """Row queries (class 2) and column queries (class 1) must be returned separately."""
    from pdf2xlsx.engines.tabletransformer import _recognize_structure
    # 2 queries: one row (class 2), one column (class 1)
    # Classes: 0=table, 1=col, 2=row, 3=col_header, 4=proj_row, 5=spanning, 6=bg
    logits = np.array([[
        [-5, -5, 10, -5, -5, -5, -5],   # query 0: row (class 2)
        [-5, 10, -5, -5, -5, -5, -5],   # query 1: col (class 1)
    ]], dtype=np.float32)
    pred_boxes = np.array([[
        [0.5, 0.3, 0.8, 0.1],   # row bbox (y1≈0.25, y2≈0.35 in 100px → 25,35)
        [0.2, 0.5, 0.1, 0.9],   # col bbox (x1≈0.15, x2≈0.25 in 100px → 15,25)
    ]], dtype=np.float32)
    sess = _make_struct_session(logits, pred_boxes)
    rows, cols = _recognize_structure(sess, np.zeros((1, 3, 100, 100), dtype=np.float32), (100, 100))
    assert len(rows) == 1
    assert len(cols) == 1


def test_recognize_structure_filters_background_queries():
    """Queries dominated by background (last class) must be excluded."""
    from pdf2xlsx.engines.tabletransformer import _recognize_structure
    logits = np.array([[
        [-5, -5, -5, -5, -5, -5, 10],   # background wins → filtered
    ]], dtype=np.float32)
    pred_boxes = np.array([[[0.5, 0.5, 0.4, 0.3]]], dtype=np.float32)
    sess = _make_struct_session(logits, pred_boxes)
    rows, cols = _recognize_structure(sess, np.zeros((1, 3, 100, 100), dtype=np.float32), (100, 100))
    assert rows == []
    assert cols == []


def test_recognize_structure_rows_sorted_by_y_cols_by_x():
    """Rows must be sorted top-to-bottom (ascending y), cols left-to-right (ascending x)."""
    from pdf2xlsx.engines.tabletransformer import _recognize_structure
    # Two rows: second one appears first in the query list
    logits = np.array([[
        [-5, -5, 10, -5, -5, -5, -5],   # row at y≈0.7
        [-5, -5, 10, -5, -5, -5, -5],   # row at y≈0.2
    ]], dtype=np.float32)
    pred_boxes = np.array([[
        [0.5, 0.7, 0.8, 0.1],  # row at cy=0.7
        [0.5, 0.2, 0.8, 0.1],  # row at cy=0.2
    ]], dtype=np.float32)
    sess = _make_struct_session(logits, pred_boxes)
    rows, _ = _recognize_structure(sess, np.zeros((1, 3, 100, 100), dtype=np.float32), (100, 100))
    assert len(rows) == 2
    assert rows[0][0] < rows[1][0], "Rows must be sorted top-to-bottom"


# ---------------------------------------------------------------------------
# 5. Engine integration: must be registered as the 4th engine
# ---------------------------------------------------------------------------

def test_tabletransformer_engine_in_engine_fns(annual_report):
    """extract_tables must invoke all 4 engines including tabletransformer."""
    import time
    from unittest.mock import patch
    from pdf2xlsx.extractor import extract_tables

    called = set()

    def spy_engine(name):
        def engine(path, **kw):
            called.add(name)
            return []
        return engine

    with patch("pdf2xlsx.extractor._extract_pdfplumber",     spy_engine("pdfplumber")), \
         patch("pdf2xlsx.extractor._extract_pymupdf",         spy_engine("pymupdf")), \
         patch("pdf2xlsx.extractor._extract_img2table",        spy_engine("img2table")), \
         patch("pdf2xlsx.extractor._extract_tabletransformer", spy_engine("tabletransformer")):
        extract_tables(annual_report)

    assert "tabletransformer" in called, (
        f"tabletransformer engine was not called; engines called: {called}"
    )
    assert called == {"pdfplumber", "pymupdf", "img2table", "tabletransformer"}, (
        f"Expected exactly 4 engines, got: {called}"
    )


@pytest.fixture
def annual_report():
    p = Path(__file__).parent / "fixtures" / "annual_report.pdf"
    if not p.exists():
        pytest.skip("annual_report.pdf fixture not present")
    return p
