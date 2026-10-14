"""Tränar om rutmodellen på dina rättelser (redigeringsläget, E) och installerar den i PanelView.

Flöde:
  1. Rättade sidor sparas automatiskt i <datamapp>/training/images + labels (YOLO-format) när du ritar rutor.
  2. Det här skriptet delar upp dem i träning/validering (var 5:e sida valideras), finjusterar YOLO-modellen
     (mosesb/best-comic-panel-detection) på grafikkortet och mäter träffsäkerheten före/efter på valideringssidorna.
  3. Om den nya modellen är bättre exporteras den till ONNX, kvantiseras till int8 och läggs i
     <datamapp>/models/panels_int8.onnx. PanelView använder den direkt vid nästa start (sidorna detekteras om).
  4. Vill du bygga in den i programmet: kopiera filen till models/ i repot och bygg/tagga en ny version.

Kör (med .venv-export som har ultralytics + torch med CUDA):
  .venv-export/Scripts/python build_tools/train_model.py [--epochs 40] [--force]

Datamapp: Windows %LOCALAPPDATA%\\PanelView, Linux ~/.local/share/PanelView.
"""
import argparse
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panelview.store import BASE  # noqa: E402

MIN_PAGES = 30


def split(data, work):
    imgs = sorted((data / "images").glob("*.jpg"))
    pairs = [(i, data / "labels" / f"{i.stem}.txt") for i in imgs if (data / "labels" / f"{i.stem}.txt").exists()]
    random.Random(1).shuffle(pairs)
    if work.exists():
        shutil.rmtree(work)
    for part in ("train", "val"):
        (work / part / "images").mkdir(parents=True)
        (work / part / "labels").mkdir(parents=True)
    for k, (img, lab) in enumerate(pairs):
        part = "val" if k % 5 == 0 else "train"
        shutil.copy2(img, work / part / "images" / img.name)
        shutil.copy2(lab, work / part / "labels" / lab.name)
    (work / "data.yaml").write_text(
        f"path: {work.as_posix()}\ntrain: train/images\nval: val/images\nnames: {{0: panel}}\n", encoding="utf-8")
    return len(pairs)


def score(model_path, work):
    """mAP50 på valideringssidorna."""
    from ultralytics import YOLO
    r = YOLO(str(model_path)).val(data=str(work / "data.yaml"), imgsz=640, verbose=False, plots=False)
    return float(r.box.map50)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    prev = BASE / "models" / "panels_ft.pt"  # bygg vidare på förra omträningen om den finns
    ap.add_argument("--base", default=str(prev if prev.exists() else Path(__file__).parent / "best.pt"))
    ap.add_argument("--force", action="store_true", help="installera även om den inte blev bättre")
    a = ap.parse_args()
    data, work = BASE / "training", BASE / "training_run"
    n = split(data, work)
    print(f"{n} rättade sidor i {data}")
    if n < MIN_PAGES:
        print(f"För få sidor för att träna (minst {MIN_PAGES}). Rätta fler sidor med E i PanelView.")
        return
    from ultralytics import YOLO
    before = score(a.base, work)
    print(f"Före: mAP50 {before:.3f}")
    YOLO(a.base).train(data=str(work / "data.yaml"), imgsz=640, epochs=a.epochs, batch=8, patience=10,
                       project=str(work), name="ft", exist_ok=True, fliplr=0.5, mosaic=0.5, verbose=False)
    best = work / "ft" / "weights" / "best.pt"
    after = score(best, work)
    print(f"Efter: mAP50 {after:.3f}")
    if after <= before and not a.force:
        print("Inte bättre – behåller nuvarande modell (använd --force för att installera ändå).")
        return
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from onnxruntime.quantization.shape_inference import quant_pre_process
    onnx = Path(YOLO(str(best)).export(format="onnx", imgsz=640, opset=17, simplify=True, dynamic=False))
    pre = onnx.with_name("pre.onnx")
    quant_pre_process(str(onnx), str(pre))
    out = BASE / "models" / "panels_int8.onnx"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    quantize_dynamic(str(pre), str(tmp), weight_type=QuantType.QUInt8)
    tmp.replace(out)
    shutil.copy2(best, BASE / "models" / "panels_ft.pt")  # utgångspunkt för nästa omträning
    print(f"Installerad: {out}  (PanelView detekterar om sidorna vid nästa start)")


if __name__ == "__main__":
    main()
