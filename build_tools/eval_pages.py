"""Evaluates the whole AutoComix chain (CV + model + cleanup + reading order) against ground truth in YOLO format.

Metrics: found panels (share of ground-truth panels found, IoU > 0.5), wrong panels (share of found ones that do not exist),
fully correct pages (all panels found, no extra ones, correct order).
  python build_tools/eval_pages.py <folder with images/ + labels/> [--model file.onnx] [--max 300]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("data")
ap.add_argument("--model")
ap.add_argument("--max", type=int, default=300)
ap.add_argument("--log", help="lägg resultatet som en rad i den här jsonl-filen")
a = ap.parse_args()
if a.model:
    os.environ["AUTOCOMIX_MODEL"] = a.model
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autocomix import geometry as G  # noqa: E402
from autocomix.detector import detect_bytes  # noqa: E402

d = Path(a.data)
imgs = sorted((d / "images").glob("*.jpg"))[: a.max]
tp = fn = fp = exact = 0
for img in imgs:
    want = []
    for ln in (d / "labels" / f"{img.stem}.txt").read_text(encoding="utf-8").split("\n"):
        if ln.strip():
            _c, cx, cy, w, h = map(float, ln.split())
            want.append({"x": cx - w / 2, "y": cy - h / 2, "w": w, "h": h})
    want = G.order(want, False)
    cvb, ml, _ = detect_bytes(img.read_bytes())
    got = G.finalize(G.merge(cvb, ml)) or [{"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}]
    if len(want) == 1 and G.area(want[0]) > 0.6:
        want = [{"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}]  # a whole page counts as one panel
    match = [max(range(len(got)), key=lambda k: G.iou(w_, got[k])) if got else -1 for w_ in want]
    ok = [m >= 0 and G.iou(w_, got[m]) > 0.5 for w_, m in zip(want, match)]
    tp += sum(ok)
    fn += len(want) - sum(ok)
    fp += max(0, len(got) - sum(ok))
    exact += all(ok) and len(got) == len(want) and match == sorted(match)
n = len(imgs)
res = {"tid": time.strftime("%Y-%m-%d %H:%M"), "data": d.name, "modell": a.model or "inbyggd/aktiv", "sidor": n,
       "hittade_rutor": round(tp / max(tp + fn, 1), 3), "felaktiga_rutor": round(fp / max(tp + fp, 1), 3),
       "helt_ratt_sidor": round(exact / max(n, 1), 3)}
print(json.dumps(res, ensure_ascii=False))
if a.log:
    with open(a.log, "a", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
