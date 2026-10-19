"""Smoke test for auto_turn: panels that fill the screen better turned 90° are turned, others are not.

Run:  python build_tools/turn_smoke.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from autocomix import store  # noqa: E402
from second_smoke import check, grab, settle  # noqa: E402


def main():
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    tmp = Path(tempfile.mkdtemp(prefix="ac_turn_"))
    store.BASE, store.CACHE, store.STATE = tmp, tmp / "cache", tmp / "state.json"  # do not touch the user's data
    from autocomix.mainwindow import MainWindow
    # a landscape panel at the top (red) + two tall ones (green, blue)
    im = Image.new("RGB", (800, 1200), (240, 240, 240))
    d = ImageDraw.Draw(im)
    for b, c in [((30, 30, 770, 400), (200, 30, 30)), ((30, 440, 390, 1170), (30, 160, 30)),
                 ((410, 440, 770, 1170), (30, 30, 200))]:
        d.rectangle(b, outline="black", width=8, fill=c)
    im.save(tmp / "00.png")
    res = []
    w = MainWindow()
    v = w.v
    w.resize(1200, 700)
    w.show()
    v.set_opt("auto_turn", "cw")
    v.set_opt("anim", False)
    v.open(str(tmp))
    settle(v)

    def center():
        g = grab(v)
        return g.pixelColor(g.width() // 2, v.area_h() // 2)

    res.append(check("bred ruta på liggande skärm vrids inte", v.turn == 0, str(v.turn)))
    v.step(1)
    settle(v)
    res.append(check("hög ruta vrids medurs", v.turn == 90, str(v.turn)))
    px = center()
    res.append(check("den vridna rutan (grön) mitt på skärmen", px.green() > 120 and px.red() < 90, px.name()))
    g = grab(v)
    c = g.pixelColor(5, 5)
    res.append(check("svart runt den vridna rutan", c.red() < 40 and c.green() < 40, c.name()))
    s = v.view.height() * v._scale()  # the panel's long side lies along the screen's width
    res.append(check("rutan fyller bredden", s > v.width() * 0.9, f"{s:.0f}/{v.width()}"))
    p = v._to_page(QPointF(v.width() / 2, v.area_h() / 2))
    res.append(check("skärmens mitt pekar i den gröna rutan", 30 < p.x() < 390 and 440 < p.y() < 1170,
                     f"{p.x():.0f},{p.y():.0f}"))
    v.set_opt("auto_turn", "ccw")
    v.reset_zoom()
    settle(v)
    res.append(check("moturs ger -90", v.turn == -90, str(v.turn)))
    v.set_opt("auto_turn", "off")
    v.reset_zoom()
    settle(v)
    res.append(check("av: ingen vridning", v.turn == 0, str(v.turn)))
    px = center()
    res.append(check("av: samma gröna ruta", px.green() > 120 and px.red() < 90, px.name()))
    ok = all(res)
    print("ALLT OK" if ok else "FEL FINNS")
    w.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
