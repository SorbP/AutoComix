"""Panel detection with the YOLO model (mosesb/best-comic-panel-detection, Apache-2.0) via ONNX Runtime.

Replaces ultralytics/PyTorch so the program can be built into a small .exe for Windows and Linux.
The model was exported to ONNX and quantized to int8 (build_tools/export_model.py).
"""
import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

SIZE = 640


def model_path():
    """A retrained model in the user folder (build_tools/train_model.py) takes precedence over the built-in one."""
    import os
    if os.environ.get("AUTOCOMIX_MODEL"):  # for evaluating a specific model
        return Path(os.environ["AUTOCOMIX_MODEL"])
    from .store import BASE
    user = BASE / "models" / "panels_int8.onnx"
    if user.exists():
        return user
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))  # PyInstaller packar upp hit
    for p in (base / "models" / "panels_int8.onnx", Path(__file__).resolve().parent.parent / "models" / "panels_int8.onnx"):
        if p.exists():
            return p
    return None


def model_id():
    """Identity of the current model (size + modification time), so the panel cache is rebuilt when the model changes."""
    p = model_path()
    if p is None:
        return "ingen"
    st = p.stat()
    return f"{st.st_size}-{int(st.st_mtime)}"


@lru_cache(maxsize=1)
def _session(path):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = 2  # leave cores for the reader
    so.log_severity_level = 3
    return ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])


def detect(img, conf=0.25, iou=0.45, min_area_frac=0.02, max_area_frac=0.98):
    """Normalized panels [{x, y, w, h}] for a BGR image."""
    mp = model_path()
    if mp is None:
        raise FileNotFoundError("modellfilen panels_int8.onnx saknas")
    h, w = img.shape[:2]
    r = min(SIZE / h, SIZE / w)
    nh, nw = round(h * r), round(w * r)
    top, left = (SIZE - nh) // 2, (SIZE - nw) // 2
    canvas = np.full((SIZE, SIZE, 3), 114, np.uint8)
    canvas[top:top + nh, left:left + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    out = _session(str(mp)).run(None, {"images": x})[0][0]  # (5, 8400): cx, cy, w, h, score
    keep = out[4] >= conf
    cx, cy, bw, bh, sc = out[:, keep]
    boxes = np.stack([(cx - bw / 2 - left) / r, (cy - bh / 2 - top) / r, bw / r, bh / r], 1)
    idx = cv2.dnn.NMSBoxes(boxes.tolist(), sc.tolist(), conf, iou)
    res = []
    for i in np.array(idx).reshape(-1):
        x0, y0, bw_, bh_ = boxes[i]
        x0, y0 = max(x0, 0.0), max(y0, 0.0)
        x1, y1 = min(x0 + bw_, w), min(y0 + bh_, h)
        a = (x1 - x0) * (y1 - y0)
        if min_area_frac * w * h <= a <= max_area_frac * w * h:
            res.append({"x": float(x0 / w), "y": float(y0 / h), "w": float((x1 - x0) / w), "h": float((y1 - y0) / h)})
    return _nms(res, 0.65)


def _nms(ps, thr):
    from .geometry import area, iou
    out = []
    for p in sorted(ps, key=area, reverse=True):
        if all(iou(p, q) < thr for q in out):
            out.append(p)
    return out
