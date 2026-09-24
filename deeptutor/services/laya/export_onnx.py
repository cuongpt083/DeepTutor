"""Script and utility to export Laya PyTorch weights to ONNX / INT8 format."""

from __future__ import annotations

import argparse
import os
import sys


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Laya to ONNX format")
    parser.add_argument("--model-id", default="convai/laya-modernbert-en", help="Hugging Face Model ID or local path")
    parser.add_argument("--output-dir", default="data/models/laya", help="Directory to save ONNX weights")
    parser.add_argument("--quantize-int8", action="store_true", help="Quantize exported model to INT8")
    return parser.parse_args(args)


def export_model(model_id: str, output_dir: str, quantize_int8: bool = False) -> str:
    """Export model to ONNX format, optionally quantizing to INT8."""
    os.makedirs(output_dir, exist_ok=True)
    try:
        from optimum.exporters.onnx import main_export

        main_export(model_name_or_path=model_id, output=output_dir, task="text-classification")
        onnx_path = os.path.join(output_dir, "model.onnx")

        if quantize_int8:
            from onnxruntime.quantization import QuantType, quantize_dynamic

            quant_path = os.path.join(output_dir, "model_quant.onnx")
            quantize_dynamic(onnx_path, quant_path, weight_type=QuantType.QInt8)
            os.replace(quant_path, onnx_path)
        return onnx_path
    except ImportError:
        raise RuntimeError("Please install optimum[onnxruntime] to run export: pip install optimum[onnxruntime]")


def main() -> None:
    args = parse_args()
    print(f"Exporting {args.model_id} to {args.output_dir} (INT8={args.quantize_int8})...")
    try:
        path = export_model(args.model_id, args.output_dir, args.quantize_int8)
        print(f"Successfully exported ONNX model to {path}")
    except Exception as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
