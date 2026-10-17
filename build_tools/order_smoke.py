"""Röktest för läsordningen: ordningsläget (X), automatisk ordning igen (Shift+X), XY-ordning som inställning.

Sida: vänster två staplade rutor (A över C), höger en hög ruta (B). Rad för rad = A-B-C, XY = A-C-B.
Kör:  python build_tools/order_smoke.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtCore import QEventLoop, QPointF, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from panelview import store  # noqa: E402

A, C, B = (30, 30, 380, 560), (30, 600, 380, 1170), (420, 30, 770, 1170)  # pixlar på en 800x1200-sida


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def check(name, ok, info=""):
    print(f"{'OK  ' if ok else 'FEL '} {name} {info}")
    return ok


def names(v):
    """Rutornas läsordning som bokstäver, utifrån mittpunkten."""
    out = []
    for r in v.panels()[0]:
        c = r.center()
        out.append("A" if c.x() < 400 and c.y() < 580 else "C" if c.x() < 400 else "B")
    return "".join(out)


def center(box):
    return QPointF((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="pv_order_"))
    store.BASE, store.CACHE, store.STATE = tmp, tmp / "cache", tmp / "state.json"  # rör inte användarens data
    from panelview.mainwindow import MainWindow
    im = Image.new("RGB", (800, 1200), (240, 240, 240))
    d = ImageDraw.Draw(im)
    for b in (A, B, C):
        d.rectangle(b, outline="black", width=8)
    im.save(tmp / "00.png")
    Image.new("RGB", (800, 1200), (200, 200, 200)).save(tmp / "01.png")
    res = []
    w = MainWindow()
    v = w.v
    w.resize(1000, 900)
    w.show()
    v.open(str(tmp))
    for _ in range(80):
        wait(50)
        if v._spread(v.sp) is not None and v.panels()[1]:
            break
    res.append(check("standard rad för rad: A-B-C", names(v) == "ABC", names(v)))

    w._toggle("order_xy")
    res.append(check("XY-ordning på: A-C-B", names(v) == "ACB", names(v)))
    w._toggle("order_xy")
    res.append(check("XY-ordning av igen: A-B-C", names(v) == "ABC", names(v)))

    # ordningsläge: klicka C, A -> B blir sist av sig själv
    v.toggle_order()
    res.append(check("X startar redigering + ordningsläge", v.edit and v.order_pick is not None))
    v.order_click(center(C))
    v.order_click(center(C))  # dubbelklick på samma ruta räknas inte två gånger
    res.append(check("klickad ruta registreras en gång", len(v.order_pick["seq"]) == 1))
    v.order_undo()
    res.append(check("högerklick ångrar senaste", v.order_pick["seq"] == []))
    v.order_click(center(C))
    v.order_click(center(A))
    res.append(check("sista rutan läggs till automatiskt och läget avslutas", v.order_pick is None))
    res.append(check("egen ordning C-A-B gäller", names(v) == "CAB", names(v)))
    w._toggle("order_xy")
    res.append(check("egen ordning går före XY-inställningen", names(v) == "CAB", names(v)))
    w._toggle("order_xy")
    v.toggle_edit()
    res.append(check("guidat läge följer egen ordning (första målet = C)",
                     v.targets() and v.targets()[0][0].center().x() < 400 and v.targets()[0][0].center().y() > 580))

    # sparas till nästa öppning
    path = v.comic.path
    v.open(str(path))
    for _ in range(40):
        wait(50)
        if v.panels()[1]:
            break
    res.append(check("egen ordning sparad mellan öppningar", names(v) == "CAB", names(v)))

    v.order_auto()
    res.append(check("Shift+X: automatisk ordning igen", names(v) == "ABC", names(v)))
    v.toggle_order()
    w.escape()
    res.append(check("Esc avbryter ordningsläget", v.order_pick is None))
    w.close()
    ok = sum(res)
    print(f"\n{ok}/{len(res)} OK")
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())
