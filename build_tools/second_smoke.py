"""Röktest för andra skärmen: spegling och automatisk fördelning (liggande/stående).

Offscreen finns bara en skärm, så skärmvalet byts ut: andra skärmen är 1080x1920 (stående), huvudfönstret liggande.
Kör:  python build_tools/second_smoke.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from panelview import second as S, store  # noqa: E402


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def check(name, ok, info=""):
    print(f"{'OK  ' if ok else 'FEL '} {name} {info}")
    return ok


def fake_relocate(self):
    if self.mode == "off":
        return False
    self.setGeometry(0, 0, 540, 960)
    self.show()
    return True


def settle(v, n=40):
    for _ in range(n):
        wait(50)
        if v._spread(v.sp) is not None and not v.animating and v.panels()[1]:
            break
    wait(150)


def grab(wid):
    return wid.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="pv_second_"))
    store.BASE, store.CACHE, store.STATE = tmp, tmp / "cache", tmp / "state.json"  # rör inte användarens data
    S.SecondScreen.relocate = fake_relocate
    S.SecondScreen.here_wide = lambda self: False   # andra skärmen stående
    S.SecondScreen.main_wide = lambda self: True    # huvudfönstret liggande
    from panelview.mainwindow import MainWindow
    # sida 1: en liggande ruta överst + två stående; sida 2: stående helsida utan ramar (hel sida = stående)
    im = Image.new("RGB", (800, 1200), (240, 240, 240))
    d = ImageDraw.Draw(im)
    for b, c in [((30, 30, 770, 400), (200, 30, 30)), ((30, 440, 390, 1170), (30, 160, 30)),
                 ((410, 440, 770, 1170), (30, 30, 200))]:
        d.rectangle(b, outline="black", width=8, fill=c)
    im.save(tmp / "00.png")
    Image.new("RGB", (800, 1200), (230, 200, 40)).save(tmp / "01.png")
    res = []
    w = MainWindow()
    v, sc = w.v, w.second
    w.resize(1200, 700)
    w.show()
    v.open(str(tmp))
    settle(v)
    res.append(check("start: tre rutor hittade", len(v.targets()) == 3, str(len(v.targets()))))

    # 1. spegling
    w.set_second("mirror")
    wait(200)
    res.append(check("spegling: fönstret visas", sc.isVisible()))
    res.append(check("spegling: sparad i inställningar", w.state.setting("second_screen") == "mirror"))
    res.append(check("spegling: huvudfönstret inte fryst", v.frozen is None))
    g = grab(sc)
    px = g.pixelColor(g.width() // 2, g.height() // 2)
    res.append(check("spegling: samma ruta (röd) mitt på andra skärmen", px.red() > 150 and px.green() < 90,
                     px.name()))
    res.append(check("spegling: menyval markerat", w.acts["second_mirror"].isChecked()))

    # 2. fördelning: ruta 1 liggande -> huvudskärmen; ruta 2 stående -> andra skärmen
    w.set_second("auto")
    v.goto_page(0, animate=False)
    settle(v)
    res.append(check("fördelning: liggande ruta stannar på huvudskärmen", not sc.live and v.frozen is None))
    v.step(1)
    settle(v)
    res.append(check("fördelning: stående ruta går till andra skärmen", sc.live and v.frozen is not None))
    g = grab(sc)
    px = g.pixelColor(g.width() // 2, g.height() // 2)
    res.append(check("fördelning: andra skärmen visar den gröna rutan", px.green() > 120 and px.red() < 90, px.name()))
    gm = grab(v)
    pm = gm.pixelColor(gm.width() // 2, gm.height() // 2)
    res.append(check("fördelning: huvudskärmen behåller den röda rutan", pm.red() > 150 and pm.green() < 90, pm.name()))
    v.step(1)
    settle(v)
    g = grab(sc)
    px = g.pixelColor(g.width() // 2, g.height() // 2)
    res.append(check("fördelning: nästa stående ruta (blå) också på andra skärmen", px.blue() > 150, px.name()))
    v.step(-1)
    settle(v)
    v.step(-1)
    settle(v)
    res.append(check("fördelning: tillbaka till liggande ruta -> huvudskärmen live igen",
                     v.frozen is None and not sc.live))
    g = grab(sc)
    px = g.pixelColor(g.width() // 2, g.height() // 2)
    res.append(check("fördelning: andra skärmen behåller sin senaste (gröna) ruta", px.green() > 120 and px.red() < 90,
                     px.name()))

    # 3. samma orientering -> beter sig som spegling
    S.SecondScreen.here_wide = lambda self: True
    v.step(1)
    settle(v)
    res.append(check("samma orientering: ingen frysning", v.frozen is None and sc.live))
    S.SecondScreen.here_wide = lambda self: False

    # 4. egen anpassning av hela sidor (liggande sida 1600x900 på stående skärm 9:16)
    from PySide6.QtCore import QRectF
    full, mv, ar = QRectF(0, 0, 1600, 900), QRectF(800, 0, 800, 900), 9 / 16
    w.set_second_fit("screen")
    r = sc.page_view(full, mv, ar)
    res.append(check("anpassning skärm: hela sidans bredd syns", r.width() >= 1600 and r.left() <= 0, str(r)))
    w.set_second_fit("height")
    r = sc.page_view(full, mv, ar)
    res.append(check("anpassning höjd: fyller höjden och följer huvudfönstrets utsnitt (höger halva)",
                     abs(r.height() - 900) < 1 and r.center().x() > 800, str(r)))
    w.set_second_fit("width")
    r = sc.page_view(full, QRectF(0, 0, 400, 300), 16 / 9)  # stående skärm -> liggande: sida 1600 bred
    res.append(check("anpassning bredd: fyller bredden", abs(r.width() - 1600) < 1, str(r)))
    w.cycle_second_fit()
    res.append(check("Shift+F9: bredd -> höjd", w.state.setting("second_fit") == "height"))
    w.set_second_fit("screen")

    # 5. av
    w.set_second("off")
    wait(100)
    res.append(check("av: fönstret dolt och huvudfönstret live", not sc.isVisible() and v.frozen is None))
    w.cycle_second()
    res.append(check("F9-växling: av -> spegling", sc.mode == "mirror"))
    w.close()
    ok = sum(res)
    print(f"\n{ok}/{len(res)} OK")
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())
