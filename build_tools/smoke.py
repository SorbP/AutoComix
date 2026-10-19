"""Smoke test of the whole GUI without a screen, step by step. Saves screenshots in %TEMP%/pv_smoke and prints the status per step."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import autocomix.store as store
tmp = Path(tempfile.mkdtemp())
store.BASE, store.CACHE, store.STATE = tmp, tmp / "cache", tmp / "state.json"  # do not touch the user's settings
from autocomix.mainwindow import BookmarkDialog, MainWindow, OptionsDialog, ThumbDialog

OUT = Path(os.environ.get("TEMP", "/tmp")) / "pv_smoke"
OUT.mkdir(exist_ok=True)
for f in OUT.glob("*.png"):
    f.unlink()
app = QApplication([])
w = MainWindow()
w.resize(1600, 900)
w.show()
v = w.v
fails = []


def ready():
    return v._spread(v.sp) is not None and v.panels()[1] and not v.animating


def shot(name, check=None):
    w.grab().save(str(OUT / f"{name}.png"))
    ok = check() if check else True
    if not ok:
        fails.append(name)
    print(f"{'OK ' if ok else 'FEL'} {name}: sida {v.page + 1} uppslag {v.sp + 1}/{len(v.spreads)} mål {v.pidx + 1}/{len(v.targets())} | {' · '.join(v.status_parts())}", flush=True)


def act(k):
    w.acts[k].trigger()


def script():
    v.open(sys.argv[1])
    v.goto_page(30, animate=False)
    yield 20000
    shot("01_guidad", lambda: v.focus != v.view and len(v.targets()) > 1)
    act("right")
    yield 8000
    shot("02_nasta_ruta", lambda: v.pidx == 1)
    act("guided")
    yield 8000
    shot("03_sidlage", lambda: len(v.targets()) == 1)
    act("fit_width")
    yield 8000
    shot("04_bredd", lambda: len(v.targets()) > 1)
    act("next")
    yield 8000
    shot("05_bredd_steg2", lambda: v.pidx == 1)
    act("fit_screen")
    yield 8000
    act("double")
    yield 8000
    shot("06_dubbelsida", lambda: len(v.spreads[v.sp]) == 2)
    act("guided")
    yield 8000
    shot("07_dubbel_guidad", lambda: len(v.targets()) > 2)
    act("double")
    yield 8000
    act("rot_right")
    yield 8000
    shot("08_roterad", lambda: v._spread(v.sp)[0].width() > v._spread(v.sp)[0].height())
    act("rot_left")
    yield 8000
    act("auto_color")
    yield 8000
    shot("09_autofarg", lambda: v._spread(v.sp) is not None)
    act("auto_color")
    yield 8000
    act("guided")
    yield 8000
    act("zoom_200")
    yield 8000
    shot("10_zoom200", lambda: len(v.targets()) > 1)
    act("fit_screen")
    yield 8000
    act("guided")
    yield 8000
    act("magnifier")
    yield 8000
    v.mouse = v.rect().center().toPointF()
    v.update()
    yield 200
    shot("11_forstoringsglas", lambda: v.mag_on)
    act("magnifier")
    yield 8000
    act("help")
    yield 8000
    shot("12_hjalp", lambda: v.show_help)
    act("help")
    yield 8000
    act("rtl")
    yield 8000
    shot("13_hoger_till_vanster", lambda: v.rtl)
    act("rtl")
    yield 8000
    act("thumbbar")
    yield 3000
    shot("16_miniatyrlist", lambda: v.thumbbar.isVisible() and v.thumbbar.currentRow() == v.page)
    p0 = v.page
    act("right")
    yield 3000
    shot("17_ruta_med_lista_oppen", lambda: v.thumbbar.isVisible() and v.thumbbar.currentRow() == v.page)
    tgt = (p0 + 2) % len(v.comic.pages)  # two pages away, also in a short test comic
    v._thumb_picked(tgt, False)
    yield 3000
    shot("17b_klick_i_listan", lambda: v.page == tgt and v.thumbbar.isVisible() and v.area_h() < v.height())
    act("thumbbar")
    yield 500
    act("slider")
    yield 500
    shot("18_reglage", lambda: v.slider.isVisible() and v.slider.slider.value() == v.page + 1)
    act("slider")
    v.state.set_setting("slideshow_ms", 1000)
    sp0, pi0 = v.sp, v.pidx
    act("slideshow")
    yield -2600  # fixed wait
    shot("19_bildspel", lambda: v.sp == sp0 and v.pidx > pi0)
    act("slideshow")
    w.state.add_bookmark(v.comic.path, v.page, "test")
    BookmarkDialog(w).close()
    OptionsDialog(w).close()
    d = ThumbDialog(w, v)
    yield 1500
    d.grab().save(str(OUT / "14_miniatyrer.png"))
    d.close()
    print("OK dialoger", flush=True)
    act("last")
    yield 8000
    n = len(v.targets())
    for _ in range(n):
        act("next")
    shot("15_slut", lambda: v.at_end)
    print("FEL:", fails if fails else "inga", flush=True)
    w.close()
    return

gen = script()


def tick(limit=0, waited=0):
    """Run the next step when the program is ready (or after limit ms; negative = fixed wait)."""
    fixed = limit < 0
    if waited < abs(limit) and (fixed or not (waited >= 300 and ready())):
        QTimer.singleShot(100, lambda: tick(limit, waited + 100))
        return
    try:
        nxt = next(gen)
    except StopIteration:
        app.quit()
        return
    QTimer.singleShot(150, lambda: tick(nxt))


QTimer.singleShot(0, lambda: tick())
app.exec()
