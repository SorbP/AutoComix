"""Jämför ONNX int8 mot ultralytics (originalet) på sidor ur en serie. Kör med .venv-export."""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panelview import geometry as G
from panelview import ml_onnx
from ultralytics import YOLO

root = Path(sys.argv[1])
pages = sorted(p for p in root.rglob("*") if p.suffix.lower() in (".jpg", ".png"))[:: max(1, len(list(root.rglob('*.jpg'))) // 25)][:25]
yolo = YOLO(str(Path(__file__).parent / "best.pt"))
tot = match = extra = 0
for p in pages:
    img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    ref = []
    for x1, y1, x2, y2 in yolo.predict(img, conf=0.25, iou=0.45, verbose=False)[0].boxes.xyxy.cpu().numpy():
        q = {"x": x1 / w, "y": y1 / h, "w": (x2 - x1) / w, "h": (y2 - y1) / h}
        if 0.02 <= G.area(q) <= 0.98:
            ref.append(q)
    got = ml_onnx.detect(img)
    m = sum(any(G.iou(a, b) > 0.8 for b in got) for a in ref)
    tot += len(ref); match += m; extra += max(0, len(got) - m)
    print(p.name, "ref", len(ref), "onnx", len(got), "match", m)
print(f"TOTALT: {match}/{tot} originalrutor återfunna (IoU>0.8), {extra} extra")
