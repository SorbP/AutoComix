"""Jämför CoMix-rutorna (Faster R-CNN, maskinritade) med PanelViews detektering på samma sidor.

Sidor där båda är överens (alla rutor matchar med IoU > 0.75) är pålitliga träningsexempel.
  python build_tools/comix_compare.py <mapp med *.jpg + *.json> [antal att rita]
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panelview import geometry as G
from panelview.detector import detect_bytes


def comix_boxes(js):
    W, H = js["image"]["width"], js["image"]["height"]
    out = []
    for p in js.get("detections", {}).get("fasterrcnn", {}).get("panels", []):
        x0, y0, x1, y1 = p["bbox"]
        out.append({"x": x0 / W, "y": y0 / H, "w": (x1 - x0) / W, "h": (y1 - y0) / H})
    return out


def agree(a, b, thr=0.75):
    return len(a) == len(b) and all(max((G.iou(p, q) for q in b), default=0) > thr for p in a)


if __name__ == "__main__":
    d = Path(sys.argv[1])
    ndraw = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    stats = {"sidor": 0, "överens": 0, "story": 0}
    tiles = []
    for js_path in sorted(d.glob("*.json")):
        js = json.loads(js_path.read_text(encoding="utf-8"))
        if js.get("page_class") != "story":
            continue
        stats["story"] += 1
        data = (d / js["image"]["file"]).read_bytes()
        cvb, ml, _ = detect_bytes(data)
        ours = G.finalize(G.merge(cvb, ml))
        theirs = G.finalize(comix_boxes(js))
        ok = agree(ours, theirs)
        stats["sidor"] += 1
        stats["överens"] += ok
        if len(tiles) < ndraw:
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            H, W = img.shape[:2]
            t = max(3, W // 250)
            for p in theirs:
                cv2.rectangle(img, (int(p["x"] * W), int(p["y"] * H)), (int((p["x"] + p["w"]) * W), int((p["y"] + p["h"]) * H)), (0, 220, 255), t)
            for k, p in enumerate(ours):
                cv2.rectangle(img, (int(p["x"] * W) + 3 * t, int(p["y"] * H) + 3 * t), (int((p["x"] + p["w"]) * W) - 3 * t, int((p["y"] + p["h"]) * H) - 3 * t), (0, 0, 255), t)
                cv2.putText(img, str(k + 1), (int(p["x"] * W) + 8 * t, int(p["y"] * H) + 22 * t), cv2.FONT_HERSHEY_SIMPLEX, t, (0, 0, 255), 2 * t)
            cv2.putText(img, f"{js_path.stem} {'OVERENS' if ok else 'OLIKA'} ours{len(ours)} comix{len(theirs)}", (10, H - 15), cv2.FONT_HERSHEY_SIMPLEX, t * .7, (0, 0, 255), 2 * t)
            tiles.append(cv2.resize(img, (400, int(400 * H / W))))
    print(stats, f"{100 * stats['överens'] / max(stats['sidor'], 1):.0f} % överens")
    if tiles:
        h = max(x.shape[0] for x in tiles)
        sheet = np.zeros((h * ((len(tiles) + 3) // 4), 1600, 3), np.uint8)
        for k, x in enumerate(tiles):
            sheet[(k // 4) * h:(k // 4) * h + x.shape[0], (k % 4) * 400:(k % 4 + 1) * 400] = x
        cv2.imwrite(os.path.join(os.environ.get("TEMP", "/tmp"), "pv_comix.jpg"), sheet)
