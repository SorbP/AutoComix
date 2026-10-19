"""Draws CV (green), ML (blue) and final panels (red, with reading order) for some pages of a comic.

  python build_tools/inspect_pages.py <comic folder> <start> <count> [rtl]  ->  %TEMP%/pv_inspect.jpg
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autocomix import geometry as G
from autocomix.comic import Comic
from autocomix.detector import detect_bytes

c = Comic(sys.argv[1])
start, n = int(sys.argv[2]), int(sys.argv[3])
rtl = len(sys.argv) > 4
tiles = []
for i in range(start, min(start + n, len(c.pages))):
    data = c.read(i)
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    H, W = img.shape[:2]
    cvb, ml, _ = detect_bytes(data)
    fin = G.finalize(G.merge(cvb, ml), rtl)
    t = max(3, W // 250)
    for p in cvb:
        cv2.rectangle(img, (int(p["x"] * W), int(p["y"] * H)), (int((p["x"] + p["w"]) * W), int((p["y"] + p["h"]) * H)), (0, 190, 0), t)
    for p in ml:
        cv2.rectangle(img, (int(p["x"] * W) + 2 * t, int(p["y"] * H) + 2 * t), (int((p["x"] + p["w"]) * W) - 2 * t, int((p["y"] + p["h"]) * H) - 2 * t), (255, 80, 0), t)
    for k, p in enumerate(fin):
        cv2.rectangle(img, (int(p["x"] * W) + 4 * t, int(p["y"] * H) + 4 * t), (int((p["x"] + p["w"]) * W) - 4 * t, int((p["y"] + p["h"]) * H) - 4 * t), (0, 0, 255), 2 * t)
        cv2.putText(img, str(k + 1), (int(p["x"] * W) + 10 * t, int(p["y"] * H) + 30 * t), cv2.FONT_HERSHEY_SIMPLEX, t * 1.2, (0, 0, 255), 3 * t)
    cv2.putText(img, f"s{i + 1} cv{len(cvb)} ml{len(ml)} fin{len(fin)}", (10, H - 20), cv2.FONT_HERSHEY_SIMPLEX, t * 0.8, (0, 0, 255), 2 * t)
    print(f"sida {i + 1}: cv {len(cvb)} ml {len(ml)} slutligt {len(fin)}", flush=True)
    tiles.append(cv2.resize(img, (420, int(420 * H / W))))
h = max(x.shape[0] for x in tiles)
cols = 4
rows = (len(tiles) + cols - 1) // cols
sheet = np.zeros((h * rows, 420 * cols, 3), np.uint8)
for k, x in enumerate(tiles):
    sheet[(k // cols) * h:(k // cols) * h + x.shape[0], (k % cols) * 420:(k % cols + 1) * 420] = x
cv2.imwrite(os.path.join(os.environ.get("TEMP", "/tmp"), "pv_inspect.jpg"), sheet)
