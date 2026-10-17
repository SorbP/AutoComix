"""Test utan skärm av återgång (Ctrl+L), historik, Esc, menyrad i helskärm, sidrutnät ur arkiv och zoom per ruta. Skapar egna testsidor. Användning: python build_tools/resume_smoke.py"""
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

import panelview.store as store
tmp = Path(tempfile.mkdtemp())
store.BASE, store.CACHE, store.STATE = tmp, tmp / "cache", tmp / "state.json"  # rör inte användarens data
from panelview.browser import PageSource, _PageGrid
from panelview.mainwindow import HistoryDialog, MainWindow

app = QApplication([])
fails = []


def wait(cond, t=30):
    end = time.time() + t
    while time.time() < end and not cond():
        app.processEvents()
        time.sleep(0.02)
    return cond()


def check(name, ok, info=""):
    print(("OK   " if ok else "FEL  ") + name + (f"  ({info})" if info else ""))
    ok or fails.append(name)


# testserie: 6 liggande sidor, vänster helhög ruta + två staplade till höger (som skärmbilden)
d = tmp / "bok"
d.mkdir()
for i in range(6):
    im = Image.new("RGB", (1530, 965), "white")
    g = ImageDraw.Draw(im)
    for b in ((10, 10, 760, 955), (775, 10, 1520, 480), (775, 495, 1520, 955)):
        g.rectangle(b, outline="black", width=8)
    g.text((40, 40), f"sida {i + 1}", fill="black")
    im.save(d / f"{i + 1:02d}.jpg")
cbz = tmp / "bok.cbz"
with zipfile.ZipFile(cbz, "w") as z:
    for f in sorted(d.iterdir()):
        z.write(f, f"bok/{f.name}")
BOXES = [{"x": .005, "y": .01, "w": .49, "h": .98}, {"x": .505, "y": .01, "w": .49, "h": .49},
         {"x": .505, "y": .51, "w": .49, "h": .48}]


def start(path=None, size=(1280, 800)):
    w = MainWindow(path)
    w.resize(*size)
    w.show()
    wait(lambda: False, 0.3)
    return w


def ready(w):
    v = w.v
    return v.comic is not None and v._spread(v.sp) is not None and v.panels()[1] and not v.animating


def mark(w):
    for n in w.v.comic.pages:
        w.v.user.set(n, BOXES)
    w.v.goto_page(w.v.page, animate=False)


# A: läs en bit in, stäng; start utan fil öppnar inget, Ctrl+L går tillbaka till samma sida och ruta
w = start(d)
check("öppnar serien", wait(lambda: ready(w)))
mark(w)
w.v.goto_page(3, animate=False)
wait(lambda: ready(w))
w.v.step(1)
pos = (w.v.page, w.v.pidx)
w.close()
w = start()
wait(lambda: False, 0.5)
check("öppnar inte automatiskt vid start", w.v.comic is None)
w.acts["resume"].trigger()
check("Ctrl+L öppnar senaste", wait(lambda: ready(w)))
check("samma sida och ruta", (w.v.page, w.v.pidx) == pos, f"{(w.v.page, w.v.pidx)} vs {pos}")

# B: historik
w.v.open(cbz)
wait(lambda: ready(w))
h = HistoryDialog(w)
check("historiken visar båda, senaste först", h.paths[:2] == [str(cbz), str(d)], str(h.paths))
check("position och antal sidor i historiken", "av 6" in h.t.item(1, 1).text(), h.t.item(1, 1).text())
h.reject()

# C: varje ruta på en skärm, hel och maximalt stor (liggande och stående fönster)
v = w.v
mark(w)
wait(lambda: ready(w))
for size in ((1280, 800), (700, 1200)):
    w.resize(*size)
    wait(lambda: False, 0.3)
    t = v.targets()
    check(f"{size}: ett steg per ruta", [k for _r, _p, k, _f in t] == [0, 1, 2])
    for i, (r, _p, k, _f) in enumerate(t):
        v.pidx = i
        view, _f = v._target()
        whole = view.adjusted(-1, -1, 1, 1).contains(r)
        tight = min(view.width() - r.width(), view.height() - r.height()) < 2
        check(f"{size}: ruta {k + 1} hel och maximal", whole and tight, f"vy {view.width():.0f}x{view.height():.0f}")
w.resize(1280, 800)

# D: Esc avslutar inte, menyraden dyker upp i helskärm
w.escape()
wait(lambda: False, 0.2)
check("Esc avslutar inte", w.isVisible())
w.toggle_fullscreen()
wait(lambda: False, 0.5)


def move(y):
    app.sendEvent(v, QMouseEvent(QEvent.Type.MouseMove, QPointF(300, y), QPointF(300, y), Qt.MouseButton.NoButton,
                                 Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))


move(400)
check("helskärm: menyraden dold", not w.top_bar.isVisible())
move(0)
check("helskärm: menyraden visas vid överkanten", w.top_bar.isVisible())
check("menyraden har alla menyer", len(w.top_bar.actions()) == len(w.menus))
move(500)
w._maybe_hide_top()
check("menyraden döljs igen", not w.top_bar.isVisible())
w.toggle_fullscreen()
w.close()

# E: sidrutnät direkt ur arkiv (ingen uppackning)
for p in (d, cbz):
    src = PageSource(p)
    check(f"sidkälla {p.suffix or 'mapp'}: 6 sidor", len(src.names) == 6 and src.read(5)[:2] == b"\xff\xd8")
    src.close()
seven = next((e for e in ("7z", r"C:\Program Files\7-Zip\7z.exe") if Path(e).exists() or
              subprocess.run(["where", e], capture_output=True).returncode == 0), None)
if seven:
    a7 = tmp / "bok.cb7"
    subprocess.run([seven, "a", "-t7z", str(a7), str(d / "*.jpg")], capture_output=True)
    src = PageSource(a7)
    got = sorted(i for i, b in src.stream() if b[:2] == b"\xff\xd8")
    check("7z: alla sidor strömmade i minnet", got == list(range(6)), str(got))
    src.close()
grid = _PageGrid(store.State())
grid.load(PageSource(cbz))
check("rutnätet fyller miniatyrer", wait(lambda: all(grid.item(i).icon().availableSizes() and
                                                      grid.item(i).icon().pixmap(50).toImage().pixel(25, 25) != 0xff323232
                                                      for i in range(6)), 15))
check("rutnätets förloppslist: 6/6 och dold när klar",
      grid.bar.maximum() == 6 and grid.done_n == 6 and not grid.bar.isVisible())
grid.shutdown()
if seven:
    from panelview.comic import Comic
    pcts = []
    c = Comic(a7, progress=pcts.append)
    check("uppackning av 7z rapporterar förlopp", len(c.pages) == 6 and pcts and pcts[-1] >= 90, str(pcts[-3:]))
    c.close()

# F: redigering – ta bort alla, ångra, gör om
w = start(d)
wait(lambda: ready(w))
v = w.v
mark(w)
v.toggle_edit()
name = v.comic.pages[v.page]
v.edit_clear_page()
check("Ctrl+Delete tar bort alla rutor", v.user.get(name) == [])
w.acts["edit_undo"].trigger()
check("Ctrl+Z ångrar", v.user.get(name) == BOXES)
w.acts["edit_redo"].trigger()
check("Ctrl+Alt+Z gör om", v.user.get(name) == [])
v.edit_undo_last()
v._edit_store(v.page, BOXES[:1])
check("ny ändring tömmer gör om", not v.edit_redo and v.user.get(name) == BOXES[:1])
v.edit_undo_last()
check("ångra flera steg", v.user.get(name) == BOXES)
v.toggle_edit()
w.close()
check("inget uppackat i temp", not any(Path(tempfile.gettempdir()).glob("panelview-*")))

print("KLART" if not fails else f"{len(fails)} FEL: {fails}")
sys.exit(1 if fails else 0)
