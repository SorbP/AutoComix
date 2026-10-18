"""Röktest för animerade sidor (GIF/WebP/APNG) utan skärm: avkodning, uppspelning, paus, steg, hastighet, bildspel.

Skapar syntetiska animationer (färgade rutor med siffror) i en temporär mapp och öppnar den som serie.
Kör:  python build_tools/anim_smoke.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from panelview import animation  # noqa: E402
from panelview import store  # noqa: E402
from panelview.store import State  # noqa: E402
from panelview.viewer import Viewer  # noqa: E402

COLORS = [(220, 40, 40), (40, 180, 60), (40, 80, 220), (230, 200, 40)]


def frames(n=4, size=(400, 600)):
    out = []
    for k in range(n):
        im = Image.new("RGB", size, COLORS[k % len(COLORS)])
        ImageDraw.Draw(im).text((20, 20), str(k), fill=(255, 255, 255))
        out.append(im)
    return out


def make(folder):
    fr = frames()
    fr[0].save(folder / "01_still.png")
    fr[0].save(folder / "02_anim.gif", save_all=True, append_images=fr[1:], duration=[50, 50, 50, 50], loop=0)
    fr[0].save(folder / "03_anim.webp", save_all=True, append_images=fr[1:], duration=60, loop=0)
    fr[0].save(folder / "04_anim.png", save_all=True, append_images=fr[1:], duration=70, loop=0)  # APNG
    fr[0].save(folder / "05_zero_delay.gif", save_all=True, append_images=fr[1:], duration=0, loop=0)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def check(name, ok, info=""):
    print(f"{'OK  ' if ok else 'FEL '} {name} {info}")
    return ok


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="pv_anim_"))
    store.BASE, store.CACHE, store.STATE = tmp, tmp / "cache", tmp / "state.json"  # rör inte användarens data
    make(tmp)
    res = []
    # 1. avkodning direkt
    for f, kind, n in (("01_still.png", None, 0), ("02_anim.gif", "gif", 4), ("03_anim.webp", "webp", 4),
                       ("04_anim.png", "apng", 4)):
        data = (tmp / f).read_bytes()
        d = animation.decode(data)
        res.append(check(f"decode {f}", animation.kind(data) == kind and (len(d[0]) if d else 0) == n,
                         f"kind={animation.kind(data)} rutor={len(d[0]) if d else 0} delays={d[1] if d else None}"))
    d = animation.decode((tmp / "05_zero_delay.gif").read_bytes())
    res.append(check("0 ms -> 100 ms", d and set(d[1]) == {100}, str(d[1] if d else None)))

    # 2. visning
    v = Viewer(State())
    v.state.set_setting("guided", False)
    v.state.set_setting("anim_play", True)
    v.state.set_setting("anim_speed", 1.0)
    v.resize(800, 1000)
    v.show()
    v.open(str(tmp / "02_anim.gif"))
    for _ in range(50):
        wait(50)
        if v.anim_pages():
            break
    res.append(check("GIF-sidan har animation", bool(v.anim_pages()), f"sida {v.page}, anims {list(v.anims)}"))
    if v.anim_pages():
        p = v.anim_pages()[0]
        seen = set()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 1.0:
            wait(10)
            seen.add(v.anims[p]["k"])
        res.append(check("rutorna byts", len(seen) >= 3, f"sedda {sorted(seen)} varv {v.anims[p]['loops']}"))
        res.append(check("bilden som visas = aktuell ruta", v.images[p] is v.anims[p]["f"][v.anims[p]["k"]]))
        res.append(check("räknaren visar ▶", "▶" in v.counter_text(), v.counter_text()))
        v.toggle_anim()
        k = v.anims[p]["k"]
        wait(300)
        res.append(check("paus stoppar", v.anims[p]["k"] == k and "❚❚" in v.counter_text(), v.counter_text()))
        v.anim_step(1)
        res.append(check("steg fram", v.anims[p]["k"] == (k + 1) % 4))
        v.anim_step(-1)
        res.append(check("steg bak", v.anims[p]["k"] == k))
        v.toggle_anim()
        v.set_anim_speed(4.0)
        seen.clear()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.5:
            wait(5)
            seen.add((v.anims[p]["loops"], v.anims[p]["k"]))
        res.append(check("4x hastighet", len(seen) >= 8, f"{len(seen)} rutbyten på 0,5 s"))
        v.set_anim_speed(1.0)

    # 3. bläddra: animationen börjar om, andra format spelas
    for target, label in ((2, "WebP"), (3, "APNG")):
        v.goto_page(target, animate=False)
        for _ in range(40):
            wait(50)
            if v.anim_pages():
                break
        ok = bool(v.anim_pages())
        if ok:
            p = v.anim_pages()[0]
            seen = set()
            t0 = time.monotonic()
            while time.monotonic() - t0 < 0.8:
                wait(10)
                seen.add(v.anims[p]["k"])
            ok = len(seen) >= 3
        res.append(check(f"{label}-sidan spelas", ok))
    v.goto_page(0, animate=False)
    wait(300)
    res.append(check("stillbild: ingen animation, ingen klocka", not v.anim_pages() and not v.frame_timer.isActive()))
    v.goto_page(1, animate=False)
    wait(30)
    res.append(check("tillbaka till GIF: börjar om", v.anim_pages() and v.anims[v.anim_pages()[0]]["loops"] == 0))

    # 4. bildspelet väntar ett varv (sista sidan: 4 x 100 ms = 400 ms per varv, sedan tar bildspelet slut)
    v.state.set_setting("slideshow_ms", 100)
    v.state.set_setting("slideshow_mode", "pages")
    v.goto_page(4, animate=False)
    for _ in range(40):
        wait(25)
        if v.anim_pages():
            break
    v.toggle_slideshow()
    wait(200)
    waiting = v.slideshow.isActive() and v.anims[v.anim_pages()[0]]["loops"] == 0
    wait(700)
    res.append(check("bildspel väntar på varv, går sedan vidare", waiting and not v.slideshow.isActive(),
                     f"väntade={waiting} aktivt nu={v.slideshow.isActive()}"))
    # 5. slinga: vid slutet börjar bildspelet om från första sidan och fortsätter
    v.state.set_setting("slideshow_loop", True)
    v.goto_page(4, animate=False)
    wait(50)
    v.toggle_slideshow()
    looped = False
    for _ in range(60):
        wait(25)
        if v.page == 0:
            looped = True
            break
    res.append(check("slinga: börjar om från början", looped and v.slideshow.isActive(),
                     f"sida={v.page} aktivt={v.slideshow.isActive()}"))
    v.state.set_setting("slideshow_loop", False)
    v.slideshow.stop()
    v.close_comic()
    res.append(check("stängning rensar", not v.anims and not v.frame_timer.isActive()))
    print(f"\n{sum(res)}/{len(res)} OK")
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
