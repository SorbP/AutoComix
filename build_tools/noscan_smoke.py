"""Smoke test: "Don't scan now" for image galleries. 150 pages, the question -> "Don't scan now": no detection, the pages
are shown whole, the choice is remembered for the file, Image > Scan panels now starts the detection anyway.
Run:  .venv/Scripts/python build_tools/noscan_smoke.py
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
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from autocomix import store  # noqa: E402


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


def click_later(label, always=False):
    """Clicks the button with the text label in the question box once it is open (always: tick "Always scan")."""
    def go():
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            QTimer.singleShot(100, go)
            return
        seen.extend(b.text() for b in box.buttons())
        box.checkBox().setChecked(always)
        next(b for b in box.buttons() if b.text() == label).click()
    seen = []
    QTimer.singleShot(100, go)
    return seen


def main():
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    tmp = Path(tempfile.mkdtemp(prefix="pv_noscan_"))
    store.BASE, store.CACHE, store.STATE = tmp / "data", tmp / "data" / "cache", tmp / "data" / "state.json"
    pages = tmp / "galleri"
    pages.mkdir()
    for k in range(150):
        Image.new("RGB", (400, 600), (240, 240, 240)).save(pages / f"{k:03d}.png")
    from autocomix import detector
    detector.detect_bytes = lambda data, ml_ok=True: ([], [], ml_ok)
    from autocomix.i18n import tr
    from autocomix.mainwindow import MainWindow
    w = MainWindow()
    v = w.v
    res = [check("standard: fråga", v.opt("scan_ask") is True)]
    w.show()
    done = lambda: sum(v.cache.get(p) is not None for p in v.comic.pages)  # noqa: E731

    seen = click_later(tr("Skanna inte nu"))
    v.open(str(pages))
    res += [check("frågan har tre val", len(seen) == 3 and tr("Skanna inte nu") in seen, str(seen)),
           check("ingen skanning startad", v.noscan and not v.detector.isRunning())]
    wait(500)
    res.append(check("inga sidor skannade", done() == 0, f"klara={done()}"))
    ps, ready = v.panels()
    res.append(check("sidan visas hel (klar, inga rutor)", ready and ps == [], f"ready={ready} rutor={len(ps)}"))
    v.goto_page(5, animate=False)
    res.append(check("bläddring fungerar", v.page == 5, f"sida={v.page}"))
    res.append(check("valet sparat för filen", v.state.comic(pages).get("noscan") is True))
    res.append(check("globala inställningen orörd", v.opt("scan_ask") is True))

    v.close_comic()
    v.open(str(pages))  # no question this time: the file remembers "Don't scan now"
    res.append(check("öppnas igen utan fråga, utan skanning", v.noscan and not v.detector.isRunning()))

    w.acts["scan_now"].trigger()
    res.append(check("Skanna rutor nu startar skanningen", not v.noscan and v.detector.isRunning()))
    res.append(check("valet för filen glömt", "noscan" not in v.state.comic(pages)))
    res.append(check("sidorna skannas (en sats i taget enligt Fråga -> alla)", until(lambda: done() == 150), f"klara={done()}"))

    v.close_comic()
    small = tmp / "liten"
    small.mkdir()
    for k in range(5):
        Image.new("RGB", (400, 600), (220, 220, 220)).save(small / f"{k:03d}.png")
    seen = click_later(tr("Skanna alla nu"))
    v.open(str(small))
    res.append(check("få sidor: frågar också, två val", len(seen) == 2, str(seen)))
    res.append(check("få sidor skannas efter Skanna alla", not v.noscan and v.detector.isRunning()))
    v.close_comic()
    v.open(str(small))
    res.append(check("svaret sparat för filen: ingen ny fråga", v.state.comic(small).get("scan") == "all"))

    v.close_comic()
    other = tmp / "galleri2"
    other.mkdir()
    for k in range(120):
        Image.new("RGB", (400, 600), (200, 200, 200)).save(other / f"{k:03d}.png")
    seen = click_later(tr("Skanna alla nu"), always=True)
    v.open(str(other))
    res.append(check("Skanna alltid: frågan stängs av", v.opt("scan_ask") is False and v.opt("detect_large") == "all"))
    v.close_comic()
    v.set_opt("detect_large", "none")
    third = tmp / "galleri3"
    third.mkdir()
    for k in range(120):
        Image.new("RGB", (400, 600), (180, 180, 180)).save(third / f"{k:03d}.png")
    v.open(str(third))
    res.append(check("utan fråga, Skanna inte: ingen skanning", v.noscan and not v.detector.isRunning()))
    v.set_opt("detect_large", "ask")  # value from older versions = scan all
    v.close_comic()
    fourth = tmp / "galleri4"
    fourth.mkdir()
    Image.new("RGB", (400, 600), (160, 160, 160)).save(fourth / "000.png")
    v.open(str(fourth))
    res.append(check("gammalt värde ask utan fråga: skannar", not v.noscan and v.detector.isRunning()))

    # left twice on the first page -> previous file, on its last page (galleri3 comes before galleri4)
    v.set_opt("guided", False)
    v.goto_page(0, animate=False)
    v.step(-1)
    res.append(check("första vänster: stannar kvar", Path(v.comic.path) == fourth and v.at_start))
    v.step(-1)
    res.append(check("andra vänster: förra filen, sista sidan",
                     Path(v.comic.path) == third and v.page == len(v.comic.pages) - 1,
                     f"{Path(v.comic.path).name} sida {v.page}"))
    w.close()
    print(f"\n{sum(res)}/{len(res)} OK")
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
