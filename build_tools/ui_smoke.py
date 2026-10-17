"""Röktest för gränssnittets storlek, avståndsläget (räknaren döljs vid inaktivitet) och förstoringsglasets former.

Kör:  python build_tools/ui_smoke.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtCore import QEvent, QEventLoop, QPointF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from panelview import store  # noqa: E402


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def check(name, ok, info=""):
    print(f"{'OK  ' if ok else 'FEL '} {name} {info}")
    return ok


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="pv_ui_"))
    store.BASE, store.CACHE, store.STATE = tmp, tmp / "cache", tmp / "state.json"  # rör inte användarens data
    from panelview.mainwindow import MainWindow
    from panelview.viewer import MAG_SHAPES
    for k in range(3):
        im = Image.new("RGB", (800, 1200), (240, 240, 240))
        d = ImageDraw.Draw(im)
        for b in [(30, 30, 770, 580), (30, 620, 390, 1170), (410, 620, 770, 1170)]:
            d.rectangle(b, outline="black", width=8)
        d.text((60, 60), f"sida {k + 1}", fill="black")
        im.save(tmp / f"{k:02d}.png")
    res = []
    w = MainWindow()
    v = w.v
    w.resize(1000, 900)
    w.show()
    v.open(str(tmp))
    for _ in range(60):
        wait(50)
        if v._spread(v.sp) is not None:
            break
    base_pt = app.font().pointSizeF()

    # 1. storlek
    w.ui_scale_step(1)
    res.append(check("större gränssnitt: appens typsnitt växer", app.font().pointSizeF() > base_pt,
                     f"{base_pt} -> {app.font().pointSizeF()}"))
    res.append(check("visningens typsnitt följer", v.font(10).pointSize() > 10, str(v.font(10).pointSize())))
    w.ui_scale_step(-1)
    res.append(check("tillbaka till 100 %", abs(v.base_ui_scale() - 1.0) < 1e-6 and
                     abs(app.font().pointSizeF() - base_pt) < 0.01))

    # 2. avståndsläge
    v.state.set_setting("counter_hide_ms", 400)
    w.acts["distance"].trigger()
    res.append(check("avståndsläge på", v.opt("distance_mode") and abs(v.ui_scale() - 1.5) < 1e-6,
                     f"ui {v.ui_scale()}"))
    res.append(check("hela gränssnittet större i avståndsläget", app.font().pointSizeF() > base_pt * 1.4))
    app.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Shift, Qt.KeyboardModifier.NoModifier))
    res.append(check("räknaren syns efter aktivitet", v.counter_visible()))
    wait(600)
    res.append(check("räknaren döljs efter 0,4 s utan aktivitet", not v.counter_visible()))
    app.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Shift, Qt.KeyboardModifier.NoModifier))
    res.append(check("tangent visar den igen", v.counter_visible()))
    shot = v.grab().toImage()
    res.append(check("ritar utan fel i avståndsläget", not shot.isNull()))
    w.acts["distance"].trigger()
    res.append(check("avståndsläge av: räknaren alltid synlig", not v.opt("distance_mode") and v.counter_visible()
                     and abs(app.font().pointSizeF() - base_pt) < 0.01))

    # 3. förstoringsglas
    v.mouse = QPointF(500, 450)
    for k, label in MAG_SHAPES:
        v.set_mag_shape(k)
        box = v.mag_box()
        img = v.grab().toImage()
        ok = not img.isNull()
        if k == "rect":
            ok = ok and abs(box.height() / box.width() - v.opt("mag_aspect")) < 0.01
        elif k in ("square", "circle", "lens"):
            ok = ok and abs(box.height() - box.width()) < 0.5
        res.append(check(f"glas: {label}", ok, f"{int(box.width())}x{int(box.height())}"))
    size = v.opt("mag_size")
    v.mag_resize(1.15)
    res.append(check("större glas", v.opt("mag_size") > size))
    z = v.opt("mag_zoom")
    v.mag_zoom_step(1.25)
    res.append(check("mer förstoring", v.opt("mag_zoom") > z))
    v.toggle_magnifier()
    # sortering efter ändringsdatum (Ctrl+D): 02 äldst -> först; samma bild visas efter omsorteringen
    import os
    for k in range(3):
        os.utime(tmp / f"{k:02d}.png", (1_600_000_000 - k * 60,) * 2)
    v.goto_page(v.comic.pages.index("00.png"), animate=False)
    w.acts["sort_mtime"].trigger()
    wait(300)
    ps = v.comic.pages
    res.append(check("Ctrl+D: sorterat efter ändringsdatum", ps.index("02.png") < ps.index("01.png") < ps.index("00.png")
                     and w.acts["sort_mtime"].isChecked(), str(ps)))
    res.append(check("Ctrl+D: står kvar på samma bild", ps[v.page] == "00.png", ps[v.page]))
    w.acts["sort_mtime"].trigger()
    wait(300)
    res.append(check("Ctrl+D igen: namnordning", v.opt("sort") == "natural" and v.comic.pages.index("00.png") == 0))
    w.close()
    print(f"\n{sum(res)}/{len(res)} OK")
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
