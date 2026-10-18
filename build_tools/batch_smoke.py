"""Röktest: 150 sidor öppnas med detect_large=batch -> bara 100 skannas, nästa sats när läsaren är nära kanten.
Kör:  .venv/Scripts/python build_tools/batch_smoke.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from panelview import store  # noqa: E402


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def check(name, ok, info=""):
    print(f"{'OK  ' if ok else 'FEL '} {name} {info}")
    return ok


def until(cond, s=60):
    t0 = time.monotonic()
    while not cond() and time.monotonic() - t0 < s:
        wait(50)
    return cond()


def main():
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    tmp = Path(tempfile.mkdtemp(prefix="pv_batch_"))
    store.BASE, store.CACHE, store.STATE = tmp / "data", tmp / "data" / "cache", tmp / "data" / "state.json"
    pages = tmp / "serie"
    pages.mkdir()
    for k in range(150):
        Image.new("RGB", (400, 600), (240, 240, 240)).save(pages / f"{k:03d}.png")
    from panelview import detector
    detector.detect_bytes = lambda data, ml_ok=True: ([], [], ml_ok)  # snabb låtsasdetektering: testet gäller satserna
    from panelview.mainwindow import MainWindow
    w = MainWindow()
    v = w.v
    v.set_opt("detect_large", "batch")
    w.show()
    v.open(str(pages))
    det = v.detector
    res = [check("sats på 100", det.batch == 100 and (det.lo, det.hi) == (0, 100), f"{det.lo}-{det.hi}")]
    done = lambda: sum(v.cache.get(p) is not None for p in v.comic.pages)  # noqa: E731
    until(lambda: done() >= 100)
    wait(500)
    res.append(check("första satsen skannad, resten väntar", done() == 100 and det.isRunning(), f"klara={done()}"))
    v.goto_page(92, animate=False)
    res.append(check("nära kanten: nästa sats", det.hi == 200, f"hi={det.hi}"))
    res.append(check("allt skannat", until(lambda: done() == 150), f"klara={done()}"))
    v.close_comic()
    v.set_opt("detect_large", "all")
    v.open(str(pages))
    res.append(check("redan skannad serie: ingen sats", v.detector is None or v.detector.batch == 0))
    w.close()
    print(f"\n{sum(res)}/{len(res)} OK")
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
