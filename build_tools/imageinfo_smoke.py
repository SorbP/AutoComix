"""Smoke test: Image info (size, PNG text / SD parameters, EXIF UserComment), Show file in folder (our browser opens
in the folder with the file selected) and Open in Explorer (command only, Explorer is not started).
Run:  .venv/Scripts/python build_tools/imageinfo_smoke.py
"""
import io
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, PngImagePlugin  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from autocomix import store  # noqa: E402


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def check(name, ok, info=""):
    print(f"{'OK  ' if ok else 'FEL '} {name} {info}")
    return ok


def main():
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    tmp = Path(tempfile.mkdtemp(prefix="pv_info_"))
    store.BASE, store.CACHE, store.STATE = tmp / "data", tmp / "data" / "cache", tmp / "data" / "state.json"
    d = tmp / "bilder med mellanslag"
    d.mkdir()
    meta = PngImagePlugin.PngInfo()
    meta.add_text("parameters", "1girl, solo\nNegative prompt: x\nSteps: 30, Sampler: Euler a, Seed: 1234")
    meta.add_text("prompt", '{"3": {"class_type": "KSampler"}}')
    for k in range(3):
        Image.new("RGB", (512, 768), (200, 100, 50)).save(d / f"{k:03d}.png", pnginfo=meta)
    ex = Image.Exif()
    ex[0x9286] = b"UNICODE\x00" + "Steps: 20, Seed: 99".encode("utf-16-be")  # A1111 in JPG
    Image.new("RGB", (300, 200)).save(d / "003.jpg", exif=ex)
    from autocomix import detector, imageinfo
    detector.detect_bytes = lambda data, ml_ok=True: ([], [], ml_ok)
    calls = []
    imageinfo.subprocess.Popen = lambda cmd, *a, **k: calls.append(cmd)
    from autocomix.mainwindow import MainWindow
    w = MainWindow()
    v = w.v
    v.set_opt("scan_ask", False)
    w.show()
    v.open(str(d))
    v.goto_page(1, animate=False)

    res = [check("current_file = bildens fil", Path(v.current_file()) == d / "001.png", v.current_file())]
    info, m = imageinfo.metadata(v.current_image()[0])
    keys = dict(m)
    res.append(check("mått och format", info["size"] == (512, 768) and info["format"] == "PNG", str(info)))
    res.append(check("SD-parametrar läses", "Seed: 1234" in keys.get("parameters", "")))
    res.append(check("ComfyUI-JSON indenterad", "\n" in keys.get("prompt", "") and "KSampler" in keys["prompt"]))
    _, mj = imageinfo.metadata((d / "003.jpg").read_bytes())
    res.append(check("EXIF UserComment (A1111 JPG)", dict(mj).get("EXIF UserComment") == "Steps: 20, Seed: 99", str(mj)))

    dlg = imageinfo.ImageInfoDialog(w, v)
    txt = dlg.text.toPlainText()
    res.append(check("inforutan visar allt", "512 × 768" in txt and "Seed: 1234" in txt and "001.png" in txt))
    dlg.close()

    w.acts["explorer"].trigger()
    res.append(check("Öppna i Utforskaren: explorer /select", calls and calls[-1] == f'explorer /select,"{d / "001.png"}"',
                     str(calls[-1:])))

    from autocomix import browser
    seen = {}

    def grab():
        dl = next((x for x in QApplication.topLevelWidgets() if isinstance(x, browser.BrowserDialog) and x.isVisible()), None)
        if dl is None:
            QTimer.singleShot(100, grab)
            return
        def done():
            ix = dl.list.currentIndex()
            seen["cur"], seen["sel"] = dl.cur, dl.files.filePath(ix) if ix.isValid() else None
            dl.reject()
        QTimer.singleShot(1500, done)
    QTimer.singleShot(100, grab)
    w.acts["show_in_folder"].trigger()
    res.append(check("Visa fil i mapp: rätt mapp", Path(seen.get("cur", "")) == d, str(seen.get("cur"))))
    res.append(check("Visa fil i mapp: filen markerad", seen.get("sel") and Path(seen["sel"]) == d / "001.png",
                     str(seen.get("sel"))))
    w.close()
    print(f"\n{sum(res)}/{len(res)} OK")
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
