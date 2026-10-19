"""Retrains the panel model and installs it in AutoComix if the whole reader gets better.

Data:
  - Your corrected/approved pages (edit mode, E/K) in <data folder>/training. Every fifth page is kept out of
    training and only used for measuring.
  - External datasets in YOLO format with train/ and val/ (e.g. CoMix, see build_tools/comix_to_yolo.py).

Flow: fine-tune YOLO on the graphics card -> export to ONNX int8 -> measure the whole AutoComix chain (eval_pages.py)
with the old and new model on your test pages and the external validation pages -> install only if the share of
fully correct pages increases. The results are logged in <data folder>/training/historik.jsonl.

Run (with .venv-export, which has ultralytics + torch with CUDA, i.e. an NVIDIA card):
  .venv-export/Scripts/python build_tools/train_model.py [--extra datasets/comix_yolo] [--epochs 40] [--force]
Data folder: Windows %LOCALAPPDATA%\\AutoComix, Linux ~/.local/share/AutoComix.
"""
import argparse
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autocomix.store import BASE  # noqa: E402

AUTOCOMIX_PY = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def user_split(work):
    """Your pages -> work/user/{train,val}. Returns (number train, number val)."""
    data = BASE / "training"
    pairs = [(i, data / "labels" / f"{i.stem}.txt") for i in sorted((data / "images").glob("*.jpg"))
             if (data / "labels" / f"{i.stem}.txt").exists()]
    random.Random(1).shuffle(pairs)
    n = {"train": 0, "val": 0}
    for k, (img, lab) in enumerate(pairs):
        part = "val" if k % 5 == 0 else "train"
        for sub, f in (("images", img), ("labels", lab)):
            (work / "user" / part / sub).mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, work / "user" / part / sub / f.name)
        n[part] += 1
    return n["train"], n["val"]


def evaluate(model, data_dir, log):
    r = subprocess.run([str(AUTOCOMIX_PY), str(ROOT / "build_tools" / "eval_pages.py"), str(data_dir),
                        "--model", str(model), "--max", "300", "--log", str(log)],
                       capture_output=True, text=True, encoding="utf-8")
    line = (r.stdout.strip().splitlines() or ["{}"])[-1]
    print("  ", line)
    try:
        return json.loads(line)
    except ValueError:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=8)
    prev = BASE / "models" / "panels_ft.pt"  # build on the previous retraining if there is one
    ap.add_argument("--base", default=str(prev if prev.exists() else ROOT / "build_tools" / "best.pt"))
    default_extra = ROOT / "datasets" / "comix_yolo"
    ap.add_argument("--extra", nargs="*", default=[str(default_extra)] if default_extra.exists() else [])
    ap.add_argument("--force", action="store_true", help="installera även om den inte blev bättre")
    a = ap.parse_args()

    work = BASE / "training_run"
    if work.exists():
        shutil.rmtree(work)
    ntr, nval = user_split(work)
    print(f"Dina sidor: {ntr} träning, {nval} prov")
    train = [str(work / "user" / "train" / "images")] if ntr else []
    val = [str(work / "user" / "val" / "images")] if nval else []
    evals = [work / "user" / "val"] if nval else []
    for e in a.extra:
        e = Path(e)
        train.append(str(e / "train" / "images"))
        val.append(str(e / "val" / "images"))
        evals.append(e / "val")
        print(f"Extern data: {e.name} ({len(list((e / 'train' / 'images').glob('*.jpg')))} träning, "
              f"{len(list((e / 'val' / 'images').glob('*.jpg')))} prov)")
    if not train or not val:
        print("Ingen träningsdata.")
        return
    (work / "data.yaml").write_text(json.dumps({"train": train, "val": val, "names": {0: "panel"}}), encoding="utf-8")

    from ultralytics import YOLO
    YOLO(a.base).train(data=str(work / "data.yaml"), imgsz=640, epochs=a.epochs, batch=a.batch, patience=10,
                       project=str(work), name="ft", exist_ok=True, fliplr=0.5, mosaic=0.5, plots=False, verbose=False)
    best = work / "ft" / "weights" / "best.pt"

    from onnxruntime.quantization import QuantType, quantize_dynamic
    from onnxruntime.quantization.shape_inference import quant_pre_process
    onnx = Path(YOLO(str(best)).export(format="onnx", imgsz=640, opset=17, simplify=True, dynamic=False))
    pre = onnx.with_name("pre.onnx")
    quant_pre_process(str(onnx), str(pre))
    cand = work / "panels_int8.onnx"
    quantize_dynamic(str(pre), str(cand), weight_type=QuantType.QUInt8)

    cur = BASE / "models" / "panels_int8.onnx"
    old = cur if cur.exists() else ROOT / "models" / "panels_int8.onnx"
    log = BASE / "training" / "historik.jsonl"
    better = True
    for d in evals:
        print(f"Mäter på {d}:")
        r_old, r_new = evaluate(old, d, log), evaluate(cand, d, log)
        better &= r_new.get("helt_ratt_sidor", 0) >= r_old.get("helt_ratt_sidor", 0)
    if not better and not a.force:
        print("Inte bättre överallt – behåller nuvarande modell (använd --force för att installera ändå).")
        return
    cur.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cand, cur.with_suffix(".tmp"))
    cur.with_suffix(".tmp").replace(cur)
    shutil.copy2(best, BASE / "models" / "panels_ft.pt")
    print(f"Installerad: {cur}  (AutoComix detekterar om sidorna vid nästa start)")


if __name__ == "__main__":
    main()
