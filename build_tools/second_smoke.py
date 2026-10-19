"""Smoke test for the second screen: mirroring and automatic distribution (landscape/portrait).

Offscreen there is only one screen, so the screen choice is replaced: the second screen is 1080x1920 (portrait), the main window landscape.
Run:  python build_tools/second_smoke.py
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

from autocomix import second as S, store  # noqa: E402


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
    store.BASE, store.CACHE, store.STATE = tmp, tmp / "cache", tmp / "state.json"  # do not touch the user's data
    S.SecondScreen.relocate = fake_relocate
    S.SecondScreen.here_wide = lambda self: False   # the second screen portrait
    S.SecondScreen.main_wide = lambda self: True    # the main window landscape
    from autocomix.mainwindow import MainWindow
    # page 1: a landscape panel at the top + two portrait ones; page 2: portrait whole page without frames (whole page = portrait)
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

    # 2. distribution: panel 1 landscape -> the main screen; panel 2 portrait -> the second screen
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

    # 3. same orientation -> behaves like mirroring
    S.SecondScreen.here_wide = lambda self: True
    v.step(1)
    settle(v)
    res.append(check("samma orientering: ingen frysning", v.frozen is None and sc.live))
    S.SecondScreen.here_wide = lambda self: False

    # 4. own fit of whole pages (landscape page 1600x900 on a portrait 9:16 screen)
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
    r = sc.page_view(full, QRectF(0, 0, 400, 300), 16 / 9)  # portrait screen -> landscape: page 1600 wide
    res.append(check("anpassning bredd: fyller bredden", abs(r.width() - 1600) < 1, str(r)))
    w.cycle_second_fit()
    res.append(check("Shift+F9: bredd -> höjd", w.state.setting("fit_right") == "height"))
    w.set_second_fit("original")
    r = sc.page_view(full, mv, ar)
    res.append(check("anpassning original: 100 % i andra skärmens pixlar", abs(r.width() - sc.width()) < 1, str(r)))
    w.set_second_fit("screen")

    # 4b. left (1-4) / right (numpad), separate values for mirroring and off/distribution
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from autocomix import mainwindow as MW
    w.activateWindow()
    wait(100)

    def key(k, kp=False):
        QTest.keyClick(w, k, Qt.KeyboardModifier.KeypadModifier if kp else Qt.KeyboardModifier.NoModifier)
        wait(50)
    st = w.state.setting
    res.append(check("migrering: vänster/höger-nycklar finns", all(st(k) for k in
                     ("fit_left", "fit_right", "fit_left_mirror", "fit_right_mirror"))))
    res.append(check("genvägar: 3 och Num+3 skiljs åt",
                     w.acts["fit_height"].shortcuts()[0] != w.acts["fit_right_height"].shortcuts()[0]
                     and w.acts["fit_right_height"].shortcuts()[0].toString() == "Num+3"))
    w.set_second("auto")
    w.set_fit("screen", side="left")
    w.set_fit("screen", side="right")
    key(Qt.Key.Key_3)
    res.append(check("tangent 3: vänster = höjd, höger orörd", st("fit_left") == "height" and st("fit_right") == "screen",
                     f"{st('fit_left')}/{st('fit_right')}"))
    res.append(check("tangent 3: huvudfönstret (vänster) använder höjd", v.fit() == "height"))
    res.append(check("flash-text", v.msg == "Vänster skärm: Anpassa till höjd", v.msg))
    key(Qt.Key.Key_2, kp=True)
    res.append(check("Num+2: höger = bredd, vänster orörd", st("fit_right") == "width" and st("fit_left") == "height",
                     f"{st('fit_left')}/{st('fit_right')}"))
    res.append(check("Num+2: andra skärmen (höger) använder bredd", sc.fit() == "width" and v.fit() == "height"))
    res.append(check("meny: bockar vänster höjd / höger bredd / andra skärmen bredd",
                     w.acts["fit_height"].isChecked() and w.acts["fit_right_width"].isChecked()
                     and w.acts["second_fit_width"].isChecked() and not w.acts["fit_screen"].isChecked()))
    w.set_second("mirror")
    res.append(check("spegling: egna värden (inte fördelningens)", st("fit_left_mirror") != "height" or
                     st("fit_right_mirror") != "width"))
    key(Qt.Key.Key_1)
    key(Qt.Key.Key_4, kp=True)
    res.append(check("spegling: 1 / Num+4 sätter spegelns nycklar",
                     st("fit_left_mirror") == "screen" and st("fit_right_mirror") == "original"
                     and st("fit_left") == "height" and st("fit_right") == "width"))
    res.append(check("spegling: huvudfönstret skärm, andra skärmen original", v.fit() == "screen" and sc.fit() == "original"))
    w.set_second("auto")
    res.append(check("tillbaka till fördelning: dess värden gäller igen", v.fit() == "height" and sc.fit() == "width"))
    # the main window on the right screen: the digits 1-4 then control the second screen
    old_s, old_m = S.side_of, MW.side_of
    S.side_of = MW.side_of = lambda wd: "right"
    res.append(check("huvudfönstret höger: andra skärmen = vänster", sc.side() == "left" and sc.fit() == "height"
                     and v.fit() == "width"))
    key(Qt.Key.Key_2)
    res.append(check("huvudfönstret höger: 2 ändrar andra skärmen", sc.fit() == "width" and v.fit() == "width"))
    S.side_of, MW.side_of = old_s, old_m

    class Fake:
        def __init__(self, d):
            self.d = d

        def setting(self, k, default=None):
            return self.d.get(k, default)

        def set_setting(self, k, val):
            self.d[k] = val
    # slideshow time: Ctrl+Num+/- (and Alt+Up/Down) in steps of 100 ms; Ctrl+normal +/- zooms as before
    w.set_slide_ms(1000)
    QTest.keyClick(w, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.KeypadModifier)
    wait(50)
    res.append(check("Ctrl+Num+: bildspel 1100 ms", st("slideshow_ms") == 1100, str(st("slideshow_ms"))))
    QTest.keyClick(w, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.KeypadModifier)
    QTest.keyClick(w, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.KeypadModifier)
    wait(50)
    res.append(check("Ctrl+Num-: bildspel 900 ms", st("slideshow_ms") == 900, str(st("slideshow_ms"))))
    QTest.keyClick(w, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
    wait(50)
    res.append(check("Alt+Upp: bildspel 1000 ms", st("slideshow_ms") == 1000, str(st("slideshow_ms"))))
    QTest.keyClick(w, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier)
    wait(50)
    res.append(check("Ctrl+- (vanligt): rör inte bildspelet", st("slideshow_ms") == 1000, str(st("slideshow_ms"))))
    fk = Fake({"fit": "width", "second_fit": "main"})
    S.migrate_fits(fk)
    res.append(check("migrering från fit/second_fit", fk.d["fit_left"] == fk.d["fit_left_mirror"] == "width"
                     and fk.d["fit_right"] == fk.d["fit_right_mirror"] == "main"))

    # 5. off
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
    try:
        rc = main()
    except Exception:
        import traceback
        traceback.print_exc()
        rc = 1
    sys.stdout.flush()
    os._exit(rc)  # background threads must not keep the process alive (it hung on failure)
