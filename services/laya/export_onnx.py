"""Standalone script to export Laya models to ONNX."""

import os
import sys

# Ensure DeepTutor is on sys.path if run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from deeptutor.services.laya.export_onnx import main, parse_args

if __name__ == "__main__":
    main()
