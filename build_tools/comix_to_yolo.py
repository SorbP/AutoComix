"""Unpacks CoMix shards (WebDataset .tar) into YOLO format: <out>/{train,val}/{images,labels}.

Story pages only (page_class == story). The panels are CoMix Faster R-CNN detections, cleaned with AutoComix dedupe.
  python build_tools/comix_to_yolo.py datasets/comix datasets/comix_yolo
"""
import io
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autocomix import geometry as G

src, out = Path(sys.argv[1]), Path(sys.argv[2])
n = {"train": 0, "val": 0}
for tar in sorted(src.glob("pages-*.tar")):
    part = "train" if "-train-" in tar.name else "val"
    (out / part / "images").mkdir(parents=True, exist_ok=True)
    (out / part / "labels").mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar) as t:
        members = {m.name: m for m in t.getmembers()}
        for name, m in members.items():
            if not name.endswith(".json"):
                continue
            js = json.load(t.extractfile(m))
            if js.get("page_class") != "story":
                continue
            W, H = js["image"]["width"], js["image"]["height"]
            boxes = []
            for p in js.get("detections", {}).get("fasterrcnn", {}).get("panels", []):
                x0, y0, x1, y1 = p["bbox"]
                boxes.append({"x": x0 / W, "y": y0 / H, "w": (x1 - x0) / W, "h": (y1 - y0) / H})
            boxes = G.dedupe([G.clip(b) for b in boxes if b["w"] > 0.02 and b["h"] > 0.02])
            img = members.get(js["image"]["file"])
            if not boxes or img is None:
                continue
            stem = Path(name).stem
            (out / part / "images" / f"{stem}.jpg").write_bytes(t.extractfile(img).read())
            (out / part / "labels" / f"{stem}.txt").write_text(
                "".join(f"0 {b['x'] + b['w'] / 2:.6f} {b['y'] + b['h'] / 2:.6f} {b['w']:.6f} {b['h']:.6f}\n" for b in boxes),
                encoding="utf-8")
            n[part] += 1
print(n)
