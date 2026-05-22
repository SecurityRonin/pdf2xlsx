"""
Table Transformer ONNX engine.

Uses two DETR-based models from Microsoft:
  - detect.onnx   (microsoft/table-transformer-detection)
  - structure.onnx (microsoft/table-transformer-structure-recognition)

Export them once with:
    python scripts/export_table_transformer.py

At runtime only onnxruntime is required (no torch).
"""

from __future__ import annotations

from pathlib import Path

import fitz
import numpy as np

from pdf2xlsx.models import ExtractedTable
from pdf2xlsx.postprocess import postprocess_rows

MODEL_CACHE_DIR = Path.home() / ".cache" / "pdf2xlsx" / "table_transformer"
DETECT_MODEL    = "detect.onnx"
STRUCTURE_MODEL = "structure.onnx"

# DETR class indices — detection model (3 classes including background)
_TABLE_CLASS = 0

# DETR class indices — structure model (7 classes including background)
_COL_CLASS = 1
_ROW_CLASS = 2

# Confidence thresholds
_DETECT_CONF    = 0.90
_STRUCTURE_CONF = 0.70

# ImageNet normalisation constants
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Render resolution: zoom factor relative to PDF's native 72 DPI
# At zoom 2.0 we get ~144 DPI — enough for Table Transformer without 4× memory of 3.0
_RENDER_ZOOM = 2.0


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------

def _preprocess_image(
    img,
    target_size: int = 800,
) -> tuple[np.ndarray, tuple[int, int]]:
    """
    Resize keeping aspect ratio (max side = target_size), normalise with ImageNet
    stats, return (tensor [1,3,H,W] float32, (H, W) of the resized image).
    """
    from PIL import Image as PILImage
    if not isinstance(img, PILImage.Image):
        img = PILImage.fromarray(img)
    img = img.convert("RGB")

    w, h = img.size
    scale = target_size / max(w, h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    img = img.resize((new_w, new_h), PILImage.LANCZOS)

    arr = np.array(img, dtype=np.float32) / 255.0        # [H, W, 3]
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    tensor = arr.transpose(2, 0, 1)[np.newaxis]          # [1, 3, H, W]
    return tensor, (new_h, new_w)


# ---------------------------------------------------------------------------
# Softmax (avoids scipy dependency)
# ---------------------------------------------------------------------------

def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


# ---------------------------------------------------------------------------
# Bounding box conversion
# ---------------------------------------------------------------------------

def _cxcywh_to_xyxy(boxes: np.ndarray, img_w: int, img_h: int) -> np.ndarray:
    """Convert normalised [cx,cy,w,h] → absolute [x1,y1,x2,y2] pixel coords."""
    cx, cy, bw, bh = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    x1 = (cx - bw / 2) * img_w
    y1 = (cy - bh / 2) * img_h
    x2 = (cx + bw / 2) * img_w
    y2 = (cy + bh / 2) * img_h
    return np.stack([x1, y1, x2, y2], axis=1)


# ---------------------------------------------------------------------------
# Detection post-processing
# ---------------------------------------------------------------------------

def _detect_tables(
    session,
    pixel_values: np.ndarray,
    img_size: tuple[int, int],
    threshold: float = _DETECT_CONF,
) -> list[tuple[float, float, float, float]]:
    """
    Run detection session, return (x1,y1,x2,y2) bboxes in resized-image pixels
    for every query whose table-class probability exceeds threshold.
    """
    h, w = img_size
    pixel_mask = np.ones((1, h, w), dtype=np.int64)
    logits, pred_boxes = session.run(None, {
        "pixel_values": pixel_values,
        "pixel_mask":   pixel_mask,
    })
    probs       = _softmax(logits[0])               # [queries, classes]
    table_probs = probs[:, _TABLE_CLASS]
    keep        = np.where(table_probs > threshold)[0]
    if len(keep) == 0:
        return []
    boxes = _cxcywh_to_xyxy(pred_boxes[0][keep], w, h)
    return [tuple(float(v) for v in row) for row in boxes.tolist()]


# ---------------------------------------------------------------------------
# Structure recognition post-processing
# ---------------------------------------------------------------------------

def _recognize_structure(
    session,
    pixel_values: np.ndarray,
    img_size: tuple[int, int],
    threshold: float = _STRUCTURE_CONF,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """
    Run structure session on a (cropped, resized) table image.
    Return:
      rows — list of (y1, y2) sorted top-to-bottom
      cols — list of (x1, x2) sorted left-to-right
    All coordinates are in the resized-crop image pixel space.
    """
    h, w = img_size
    pixel_mask = np.ones((1, h, w), dtype=np.int64)
    logits, pred_boxes = session.run(None, {
        "pixel_values": pixel_values,
        "pixel_mask":   pixel_mask,
    })
    probs      = _softmax(logits[0])                # [queries, classes]
    boxes_abs  = _cxcywh_to_xyxy(pred_boxes[0], w, h)

    rows: list[tuple[float, float]] = []
    cols: list[tuple[float, float]] = []

    n_classes  = probs.shape[1]
    n_data_cls = n_classes - 1                      # exclude background (last)

    for i in range(len(probs)):
        best_cls  = int(np.argmax(probs[i, :n_data_cls]))
        if probs[i, best_cls] < threshold:
            continue
        x1, y1, x2, y2 = (float(v) for v in boxes_abs[i])
        if best_cls == _ROW_CLASS:
            rows.append((y1, y2))
        elif best_cls == _COL_CLASS:
            cols.append((x1, x2))

    rows.sort(key=lambda r: r[0])
    cols.sort(key=lambda c: c[0])
    return rows, cols


# ---------------------------------------------------------------------------
# Cell text extraction (pdfplumber)
# ---------------------------------------------------------------------------

def _cell_text(pdf_page, x1: float, y1: float, x2: float, y2: float) -> str:
    PAD = 1.5
    try:
        crop = pdf_page.crop((
            max(0, x1 - PAD), max(0, y1 - PAD),
            min(pdf_page.width, x2 + PAD), min(pdf_page.height, y2 + PAD),
        ))
        return (crop.extract_text() or "").strip()
    except Exception:
        return ""


def _build_rows(
    pdf_page,
    img_rows: list[tuple[float, float]],
    img_cols: list[tuple[float, float]],
    # table bbox in detection-resized image (for origin offset)
    tbl_det_x1: float, tbl_det_y1: float,
    # scale: detection-resized pixel → PDF point
    det_to_pdf_x: float, det_to_pdf_y: float,
    # scale: structure-crop-resized pixel → original-crop pixel
    # (crop was cut from detection-resized image, then resized for structure model)
    crop_w_det: float, crop_h_det: float,   # crop size in detection-resized pixels
    struct_w: int, struct_h: int,           # structure model resized size
) -> list[list[str]]:
    """
    Map structure-model row/col boundaries → PDF coordinates and extract text.

    Coordinate chain:
      struct-resized pixel → detection-resized pixel → PDF point
    """
    # Scale from structure-model image back to detection-resized image
    sx = crop_w_det / struct_w if struct_w else 1.0
    sy = crop_h_det / struct_h if struct_h else 1.0

    def to_pdf_x(x_s: float) -> float:
        return (tbl_det_x1 + x_s * sx) * det_to_pdf_x

    def to_pdf_y(y_s: float) -> float:
        return (tbl_det_y1 + y_s * sy) * det_to_pdf_y

    result = []
    for ry1, ry2 in img_rows:
        row = []
        for cx1, cx2 in img_cols:
            x1 = to_pdf_x(cx1);  x2 = to_pdf_x(cx2)
            y1 = to_pdf_y(ry1);  y2 = to_pdf_y(ry2)
            row.append(_cell_text(pdf_page, x1, y1, x2, y2))
        result.append(row)
    return result


# ---------------------------------------------------------------------------
# ONNX session loader
# ---------------------------------------------------------------------------

def _load_session(model_path: Path):
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.inter_op_num_threads = 2
    opts.intra_op_num_threads = 2
    opts.log_severity_level   = 3   # suppress verbose ORT logs
    return ort.InferenceSession(str(model_path), sess_options=opts)


# ---------------------------------------------------------------------------
# Public engine entry point
# ---------------------------------------------------------------------------

def _extract_tabletransformer(path: Path, **_) -> list[ExtractedTable]:
    """
    Table Transformer ONNX engine.

    Returns [] gracefully if:
    - ONNX model files are absent from MODEL_CACHE_DIR
    - onnxruntime is not installed
    - Any page-level error occurs (continues to next page)
    """
    detect_path    = MODEL_CACHE_DIR / DETECT_MODEL
    structure_path = MODEL_CACHE_DIR / STRUCTURE_MODEL

    if not detect_path.exists() or not structure_path.exists():
        return []

    try:
        detect_sess    = _load_session(detect_path)
        structure_sess = _load_session(structure_path)
    except Exception:
        return []

    from PIL import Image as PILImage
    import pdfplumber

    tables: list[ExtractedTable] = []

    try:
        fitz_doc = fitz.open(str(path))
        pdf      = pdfplumber.open(str(path))
    except Exception:
        return []

    try:
        for page_num, fitz_page in enumerate(fitz_doc, start=1):
            try:
                mat = fitz.Matrix(_RENDER_ZOOM, _RENDER_ZOOM)
                pix = fitz_page.get_pixmap(matrix=mat, alpha=False)
                img = PILImage.frombytes("RGB", [pix.width, pix.height], pix.samples)
                orig_w, orig_h = img.size   # rendered image dimensions (pixels)

                pixel_values, (det_h, det_w) = _preprocess_image(img)
                det_scale_x = det_w / orig_w
                det_scale_y = det_h / orig_h

                table_bboxes = _detect_tables(detect_sess, pixel_values, (det_h, det_w))
                if not table_bboxes:
                    continue

                pdf_page = pdf.pages[page_num - 1]
                # 1 PDF point = _RENDER_ZOOM pixels in the rendered image, so:
                # pdf_x = rendered_pixel / _RENDER_ZOOM
                # detection-resized pixel → PDF point:
                det_to_pdf_x = 1.0 / (det_scale_x * _RENDER_ZOOM)
                det_to_pdf_y = 1.0 / (det_scale_y * _RENDER_ZOOM)

                for idx, (tx1, ty1, tx2, ty2) in enumerate(table_bboxes):
                    # Crop detection-resized image to table region
                    cx1 = max(0, int(tx1)); cy1 = max(0, int(ty1))
                    cx2 = min(det_w, int(tx2)); cy2 = min(det_h, int(ty2))
                    if cx2 <= cx1 or cy2 <= cy1:
                        continue

                    # Reconstruct PIL image from normalised tensor for cropping
                    arr = pixel_values[0].transpose(1, 2, 0)         # [H,W,3]
                    arr = arr * _IMAGENET_STD + _IMAGENET_MEAN        # de-normalise
                    arr = np.clip(arr * 255, 0, 255).astype(np.uint8)
                    full_det_img = PILImage.fromarray(arr)
                    table_crop   = full_det_img.crop((cx1, cy1, cx2, cy2))

                    crop_w_det = cx2 - cx1
                    crop_h_det = cy2 - cy1

                    struct_tensor, (struct_h, struct_w) = _preprocess_image(table_crop)
                    img_rows, img_cols = _recognize_structure(
                        structure_sess, struct_tensor, (struct_h, struct_w)
                    )
                    if not img_rows or not img_cols:
                        continue

                    raw_rows = _build_rows(
                        pdf_page,
                        img_rows, img_cols,
                        tx1, ty1,
                        det_to_pdf_x, det_to_pdf_y,
                        crop_w_det, crop_h_det,
                        struct_w, struct_h,
                    )

                    from pdf2xlsx.extractor import _clean_rows, _is_meaningful_table
                    cleaned = postprocess_rows(_clean_rows(raw_rows))
                    if _is_meaningful_table(cleaned):
                        tables.append(ExtractedTable(
                            page=page_num, index=idx,
                            rows=cleaned, source="tabletransformer",
                        ))

            except Exception:
                continue
    finally:
        pdf.close()
        fitz_doc.close()

    return tables
