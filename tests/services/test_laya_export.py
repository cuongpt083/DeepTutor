import pytest
from deeptutor.services.laya.export_onnx import parse_args


def test_parse_args_defaults():
    args = parse_args(["--model-id", "convai/laya-modernbert-en"])
    assert args.model_id == "convai/laya-modernbert-en"
    assert args.output_dir == "data/models/laya"
    assert args.quantize_int8 is False


def test_parse_args_quantize():
    args = parse_args(["--model-id", "convai/laya-modernbert-en", "--quantize-int8", "--output-dir", "custom/dir"])
    assert args.model_id == "convai/laya-modernbert-en"
    assert args.output_dir == "custom/dir"
    assert args.quantize_int8 is True
