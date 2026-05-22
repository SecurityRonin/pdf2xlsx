#!/usr/bin/env python
"""
Export Microsoft Table Transformer models to ONNX.

Run once to populate the model cache; thereafter only onnxruntime is needed.

Requirements (install in a temporary env, not the main venv):
    pip install torch torchvision transformers onnxscript

  onnxscript is required by PyTorch 2.5+ even when using the legacy exporter path.

Usage:
    python scripts/export_table_transformer.py
    python scripts/export_table_transformer.py --cache-dir /custom/path
"""

import argparse
import sys
from pathlib import Path


DETECT_MODEL_ID    = "microsoft/table-transformer-detection"
STRUCTURE_MODEL_ID = "microsoft/table-transformer-structure-recognition"

DEFAULT_CACHE = Path.home() / ".cache" / "pdf2xlsx" / "table_transformer"


class _DETRWrapper:
    """Thin nn.Module wrapper that returns (logits, pred_boxes) as a plain tuple."""

    def __init__(self, model):
        import torch.nn as nn
        super().__init__()  # type: ignore[call-arg]
        self.model = model

    def forward(self, pixel_values, pixel_mask):
        out = self.model(pixel_values=pixel_values, pixel_mask=pixel_mask)
        return out.logits, out.pred_boxes


def _export(model_id: str, output_path: Path, force: bool = False) -> None:
    import torch
    from transformers import AutoModelForObjectDetection

    if output_path.exists() and not force:
        print(f"  Already exported — skipping ({output_path})")
        return

    print(f"  Downloading {model_id} …")
    raw = AutoModelForObjectDetection.from_pretrained(model_id)
    raw.eval()

    import torch.nn as nn

    class Wrapper(nn.Module):
        def __init__(self):
            super().__init__()
            self.m = raw

        def forward(self, pixel_values, pixel_mask):
            out = self.m(pixel_values=pixel_values, pixel_mask=pixel_mask)
            return out.logits, out.pred_boxes

    wrapper = Wrapper().eval()

    dummy_pv = torch.zeros(1, 3, 800, 800)
    dummy_pm = torch.ones(1, 800, 800, dtype=torch.long)

    print(f"  Exporting to ONNX → {output_path}")
    export_kwargs = dict(
        input_names=["pixel_values", "pixel_mask"],
        output_names=["logits", "pred_boxes"],
        dynamic_axes={
            "pixel_values": {0: "batch", 2: "height", 3: "width"},
            "pixel_mask":   {0: "batch", 1: "height", 2: "width"},
            "logits":       {0: "batch"},
            "pred_boxes":   {0: "batch"},
        },
        opset_version=14,
    )
    with torch.no_grad():
        try:
            # PyTorch ≥ 2.5: dynamo=False forces the legacy TorchScript exporter
            # and avoids the onnxscript import in the new dynamo-based path.
            torch.onnx.export(
                wrapper, (dummy_pv, dummy_pm), str(output_path),
                dynamo=False, **export_kwargs,
            )
        except TypeError:
            # Older PyTorch that doesn't accept dynamo= keyword
            torch.onnx.export(
                wrapper, (dummy_pv, dummy_pm), str(output_path),
                **export_kwargs,
            )
    print(f"  Saved {output_path} ({output_path.stat().st_size // 1_000_000} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--force", action="store_true", help="Re-export even if ONNX files exist")
    args = parser.parse_args()

    cache: Path = args.cache_dir
    cache.mkdir(parents=True, exist_ok=True)

    missing = []
    for pkg in ("torch", "transformers", "onnxscript"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"ERROR: missing packages: {', '.join(missing)}")
        print("Install:  pip install torch torchvision transformers onnxscript")
        sys.exit(1)

    print("Exporting detection model …")
    _export(DETECT_MODEL_ID, cache / "detect.onnx", force=args.force)

    print("Exporting structure-recognition model …")
    _export(STRUCTURE_MODEL_ID, cache / "structure.onnx", force=args.force)

    print(f"\nDone. Models cached at: {cache}")
    print("Run pdf2xlsx normally — tabletransformer engine will activate automatically.")


if __name__ == "__main__":
    main()
