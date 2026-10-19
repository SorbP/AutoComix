"""Artificial comic pages for testing panel detection and reading order without real comics.

Variants: white gutters with a frame, black lines as the only separation, white page margin + black gutters.
  python build_tools/synthetic_pages.py   ->  hits per variant
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autocomix import geometry as G
from autocomix.detector import detect_bytes

H, W = 1165, 901
LAYOUTS = [  # (x, y, w, h) i pixlar, i facit-ordning
    [(12, 12, 226, 505), (244, 12, 256, 505), (506, 12, 383, 505),
     (12, 527, 190, 626), (208, 527, 262, 626), (476, 527, 135, 626), (617, 527, 272, 626)],
    [(12, 12, 877, 300), (12, 322, 430, 400), (452, 322, 437, 400), (12, 732, 280, 421), (302, 732, 280, 421), (592, 732, 297, 421)],
    [(12, 12, 420, 560), (442, 12, 447, 275), (442, 297, 447, 275), (12, 582, 877, 571)],
]


def page(boxes, style, seed):
    rng = np.random.default_rng(seed)
    bg = {"white": 255, "black": 20, "margin": 255}[style]
    img = np.full((H, W, 3), bg, np.uint8)
    if style == "margin":
        img[8:H - 8, 8:W - 8] = 20
    for x, y, w, h in boxes:
        if style == "white":
            x, y, w, h = x + 8, y + 8, w - 16, h - 16
        sub = np.empty((h, w, 3), np.uint8)
        sub[:] = rng.integers(90, 230, 3)
        for _ in range(30):  # "drawing" inside the panel, including dark areas
            cv2.circle(sub, (int(rng.integers(0, w)), int(rng.integers(0, h))), int(rng.integers(8, 50)),
                       tuple(int(c) for c in rng.integers(0, 255, 3)), -1)
        cv2.ellipse(sub, (w // 2, h // 3), (w // 4, h // 7), 0, 0, 360, (255, 255, 255), -1)
        img[y:y + h, x:x + w] = sub
        if style == "white":
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 0), 4)
    return img


def check(boxes, img):
    cvb, ml, _ = detect_bytes(cv2.imencode(".jpg", img)[1].tobytes())
    fin = G.finalize(G.merge(cvb, ml))
    exp = [{"x": x / W, "y": y / H, "w": w / W, "h": h / H} for x, y, w, h in boxes]
    got = [max(range(len(exp)), key=lambda k: G.iou(exp[k], p)) + 1 for p in fin]
    return got == list(range(1, len(boxes) + 1)), got, len(cvb), len(ml)


if __name__ == "__main__":
    for li, boxes in enumerate(LAYOUTS):
        for style in ("white", "black", "margin"):
            ok, got, nc, nm = check(boxes, page(boxes, style, li))
            print(f"layout {li + 1} {style:6} {'OK ' if ok else 'FEL'} ordning {got} (cv {nc}, ml {nm})", flush=True)
