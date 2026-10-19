"""Exports the YOLO model to ONNX and quantizes to int8 (run with .venv-export, which has ultralytics).

  python build_tools/export_model.py build_tools/best.pt  ->  models/panels_int8.onnx
"""
import sys
from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic
from onnxruntime.quantization.shape_inference import quant_pre_process
from ultralytics import YOLO

pt = Path(sys.argv[1])
onnx = Path(YOLO(str(pt)).export(format="onnx", imgsz=640, opset=17, simplify=True, dynamic=False))
pre = onnx.with_name("best_pre.onnx")
quant_pre_process(str(onnx), str(pre))
out = Path(__file__).resolve().parents[1] / "models" / "panels_int8.onnx"
quantize_dynamic(str(pre), str(out), weight_type=QuantType.QUInt8)
print(out)
