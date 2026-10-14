"""Visningsytan: sidor/uppslag, guidad zoom ruta för ruta, anpassningslägen, förstoringsglas, bildspel.

Navigeringen går genom en lista "mål" per uppslag: rutor (guidat läge) eller visningsfönster enligt
anpassningsläget (skärm/bredd/höjd/originalstorlek). Pil/klick/hjul stegar genom målen och sedan till nästa uppslag.
"""
from pathlib import Path

import numpy as np
from PySide6.QtCore import (QEasingCurve, QObject, QPointF, QRectF, QRunnable, Qt, QThreadPool, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import geometry as G
from . import imaging
from .comic import IMAGE_EXT, Comic, PasswordNeeded
from .detector import Detector
from .overlays import PageSlider, ThumbBar
from .store import PanelCache, State, UserPanels, load_sidecar, save_training_example

MARGIN = 0.012     # luft runt rutan, andel av sidan
SCROLL_OVERLAP = 0.1  # överlapp när en sida visas i flera steg (anpassa bredd/höjd/zoom)
KEEP_SPREADS = 3   # uppslag före/efter som hålls i minnet

DEFAULTS = {
    "guided": True, "overview": False, "dim": True,
    "fit": "screen", "zoom": 1.0,
    "shrink_w": True, "grow_w": True, "shrink_h": True, "grow_h": True,  # CDisplayEx: över/under bredd/höjd
    "double": False, "cover_single": True, "shadow": True,
    "rotation": 0, "auto_color": False, "gamma": 1.0, "vibrance": 0.0,
    "bg": "#0c0c0c", "quality": "smooth", "anim": True, "anim_ms": 320,
    "slideshow_ms": 5000, "slideshow_mode": "guided", "slideshow_next_file": False, "auto_next_file": True, "history": True, "clear_history_on_exit": False,
    "sort": "natural", "resume_on_start": False, "hide_cursor": True,
    "show_pagenum": True, "show_progress": True, "mag_size": 320, "mag_zoom": 2.0,
}


def lerp_rect(a, b, t):
    return QRectF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t,
                  a.width() + (b.width() - a.width()) * t, a.height() + (b.height() - a.height()) * t)


def rotate_box(p, rot):
    """Normaliserad ruta efter att sidan roterats rot grader medurs."""
    x, y, w, h = p["x"], p["y"], p["w"], p["h"]
    rot %= 360
    if rot == 90:
        return {"x": 1 - y - h, "y": x, "w": h, "h": w}
    if rot == 180:
        return {"x": 1 - x - w, "y": 1 - y - h, "w": w, "h": h}
    if rot == 270:
        return {"x": y, "y": 1 - x - w, "w": h, "h": w}
    return p


def _steps(total, view):
    """Startpositioner för ett fönster av storlek view över längden total, med överlapp, sista mot kanten."""
    if view >= total:
        return [(total - view) / 2]
    out, x, step = [], 0.0, view * (1 - SCROLL_OVERLAP)
    while x + view < total:
        out.append(x)
        x += step
    out.append(total - view)
    return out


class _Sig(QObject):
    loaded = Signal(int, QImage, int)  # sida, bild, generation


class _Load(QRunnable):
    def __init__(self, comic, i, sig, opts, gen):
        super().__init__()
        self.comic, self.i, self.sig, self.opts, self.gen = comic, i, sig, opts, gen

    def run(self):
        try:
            img = QImage.fromData(self.comic.read(self.i))
            img = imaging.process(img, **self.opts)
        except Exception:
            img = QImage()
        try:
            self.sig.loaded.emit(self.i, img, self.gen)
        except RuntimeError:  # fönstret stängdes medan sidan laddades
            pass


class Viewer(QWidget):
    changed = Signal()                 # titel/sida/läge ändrat (för menyer och fönstertitel)
    contextMenu = Signal(QPointF)      # högerklick
    passwordNeeded = Signal(str)       # krypterat arkiv
    finished = Signal()                # slutet av serien nått (för "nästa fil")

    def __init__(self, state=None):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(320, 240)
        self.state = state or State()
        self.comic = self.detector = self.cache = None
        self.sidecar, self.rtl = {}, False
        self.images, self.sizes, self.loading = {}, {}, set()
        self.gen = 0
        self.spreads, self.sp_of, self.sp_cache = [], {}, {}
        self.sp = 0
        self.page = 0
        self.pidx = 0
        self.sig = _Sig()
        self.sig.loaded.connect(self._on_loaded)
        self.pool = QThreadPool.globalInstance()
        self.view = self.focus = QRectF()
        self.a0 = self.a1 = self.f0 = self.f1 = QRectF()
        self.animating = self.free = self.pending_entry = False
        self.custom = None
        self.show_help, self.help_text = False, ""
        self.hud_always = False
        self.msg, self.progress = "", (0, 0)
        self.drag = None
        self.wheel_acc = 0
        self.at_end = False
        self.mag_on = self.mag_hold = False
        self.edit, self.edit_drag, self.edit_undo = False, None, []
        self.user = None
        self.mouse = QPointF()
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=self.opt("anim_ms"),
                                      easingCurve=QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._tick)
        self.anim.finished.connect(self._anim_done)
        self.hud_timer = QTimer(self, singleShot=True, interval=2500, timeout=self.update)
        self.slideshow = QTimer(self, timeout=self._slide)
        self.cursor_timer = QTimer(self, singleShot=True, interval=2000, timeout=self._hide_cursor)
        self.thumbbar = ThumbBar(self)
        self.thumbbar.picked.connect(self._thumb_picked)
        self.slider = PageSlider(self)
        self.slider.picked.connect(lambda i: self.goto_page(i))
        self.changed.connect(self._sync_overlays)

    # ---------- inställningar ----------
    def opt(self, k):
        return self.state.setting(k, DEFAULTS.get(k))

    def set_opt(self, k, v):
        self.state.set_setting(k, v)
        if k in ("rotation", "auto_color", "gamma", "vibrance"):
            self.reload_images()
        elif k in ("double", "cover_single"):
            self._layout(keep_page=True)
        elif k == "shadow":
            self.sp_cache.clear()
            self.goto_page(self.page, animate=False)
        elif k == "anim_ms":
            self.anim.setDuration(v)
        elif k == "slideshow_ms" and self.slideshow.isActive():
            self.slideshow.start(int(v))
        elif k == "sort" and self.comic:
            self.open(self.comic.path)
        elif self.comic:
            self.free, self.custom = False, None
            self._clamp_retarget(animate=False)
        self.changed.emit()
        self.update()

    # ---------- serie ----------
    def open(self, path, password=None):
        path = Path(path)
        first = None
        if path.is_file() and path.suffix.lower() in IMAGE_EXT:  # enskild bild: öppna mappen och börja på den bilden
            path, first = path.parent, path.name
        try:
            comic = Comic(path, password=password, sort=self.opt("sort"))
        except PasswordNeeded:
            self.passwordNeeded.emit(str(path))
            return False
        except Exception as e:
            self.flash(f"Kunde inte öppna: {e}")
            return False
        self.close_comic()
        self.comic = comic
        self.cache = PanelCache(path)
        self.user = UserPanels(path)
        self.sidecar = load_sidecar(path)
        self.rtl = self.state.rtl(path, comic.rtl_hint())
        start = min(self.state.comic(path).get("page", 0), len(comic.pages) - 1)
        if first:
            start = next((i for i, n in enumerate(comic.pages) if Path(n).name == first), start)
        if self.opt("history"):
            self.state.add_history(path)
        self.detector = Detector(comic, self.cache)
        self.detector.pageDone.connect(self._on_detected)
        self.detector.progress.connect(self._on_progress)
        self.detector.set_focus(start)
        self.detector.start()
        self._layout()
        self.goto_page(start, forward=True, animate=False)
        self.flash(f"{comic.title}  ({len(comic.pages)} sidor)")
        self.changed.emit()
        return True

    def close_comic(self):
        self.slideshow.stop()
        if self.detector:
            self.detector.stop()
            self.detector = None
        if self.comic:
            self.state.set_page(self.comic.path, self.page)
            self.state.save()
            self.comic.close()
        self.comic = None
        self.images.clear()
        self.sizes.clear()
        self.loading.clear()
        self.sp_cache.clear()
        self.spreads, self.sp_of = [], {}
        self.gen += 1
        self.view = self.focus = QRectF()
        self.changed.emit()
        self.update()

    def sibling(self, step):
        if not self.comic:
            return
        sib = self.comic.siblings()
        try:
            i = sib.index(self.comic.path)
        except ValueError:
            return
        if 0 <= i + step < len(sib):
            self.open(sib[i + step])
        else:
            self.flash("Ingen fler serie i mappen")

    def reload_images(self):
        """Bildinställningar ändrade (rotation/färg): ladda om sidorna, behåll position."""
        if not self.comic:
            return
        self.gen += 1
        self.images.clear()
        self.sizes.clear()
        self.loading.clear()
        self.sp_cache.clear()
        self._layout(keep_page=True)
        self.goto_page(self.page, animate=False)

    # ---------- uppslag ----------
    def _landscape(self, i):
        s = self.sizes.get(i)
        return bool(s) and s[0] > s[1] * 1.05

    def _layout(self, keep_page=False):
        """Delar upp sidorna i uppslag. Liggande sidor och (valfritt) omslaget visas ensamma."""
        if not self.comic:
            return
        n = len(self.comic.pages)
        out = []
        if not self.opt("double"):
            out = [(i,) for i in range(n)]
        else:
            i = 0
            if self.opt("cover_single") and n:
                out.append((0,))
                i = 1
            while i < n:
                if i == n - 1 or self._landscape(i) or self._landscape(i + 1):
                    out.append((i,))
                    i += 1
                else:
                    out.append((i, i + 1))
                    i += 2
        if out != self.spreads:
            self.spreads = out
            self.sp_of = {p: s for s, ps in enumerate(out) for p in ps}
            self.sp_cache.clear()
            if keep_page:
                self.goto_page(self.page, animate=False)

    def _spread(self, s):
        """(bild, sidrektanglar i visningsordning, sidor i visningsordning) eller None om inte laddat."""
        if s in self.sp_cache:
            return self.sp_cache[s]
        pages = self.spreads[s]
        if any(p not in self.images for p in pages):
            return None
        order = list(reversed(pages)) if self.rtl else list(pages)
        img, rects = imaging.spread([self.images[p] for p in order], shadow=self.opt("shadow"))
        bg = imaging.edge_color(img) if self.opt("bg") == "auto" else QColor(self.opt("bg"))
        self.sp_cache[s] = (img, rects, order, bg)
        return self.sp_cache[s]

    def _page_panels(self, i):
        """(rutor normaliserade för sidan, klar?)."""
        name = self.comic.pages[i]
        sc = self.sidecar.get(Path(name).stem.lower())
        up = self.user.get(name) if self.user else None
        if up is not None:  # egna rutor: bara läsordningen räknas fram
            ps = G.order(up, self.rtl) if up else []
        elif sc is not None:
            ps = G.finalize(sc, self.rtl)
        else:
            c = self.cache.get(name)
            if c is None:
                return [], False
            ps = G.finalize(G.merge(c["cv"], c["ml"]), self.rtl)
        rot = self.opt("rotation")
        return [rotate_box(p, rot) for p in ps], True

    def panels(self, s=None):
        """(rutor som QRectF i uppslagets pixlar i läsordning, klar?)."""
        s = self.sp if s is None else s
        sp = self._spread(s)
        if sp is None:
            return [], False
        _img, rects, order, _bg = sp
        out, ready = [], True
        for p in self.spreads[s]:  # läsordning = sidordning
            ps, ok = self._page_panels(p)
            ready &= ok
            r = rects[order.index(p)]
            out += [QRectF(r.x() + q["x"] * r.width(), r.y() + q["y"] * r.height(), q["w"] * r.width(), q["h"] * r.height())
                    for q in ps]
        if ready and len(self.spreads[s]) > 1 and any(not self._page_panels(p)[0] for p in self.spreads[s]):
            # en av sidorna saknar rutor (helsida): visa den som en egen "ruta" i läsordning
            out = []
            for p in self.spreads[s]:
                ps, _ = self._page_panels(p)
                r = rects[order.index(p)]
                out += [QRectF(r.x() + q["x"] * r.width(), r.y() + q["y"] * r.height(), q["w"] * r.width(), q["h"] * r.height())
                        for q in ps] or [QRectF(r)]
        return out, ready

    def guided(self):
        return self.opt("guided")

    # ---------- mål ----------
    def _viewports(self, full):
        """Visningsfönster enligt anpassningsläget, i läsordning."""
        W, H = max(self.width(), 1), self.area_h()
        ar = W / H
        fit = self.opt("fit")
        if fit == "width":
            vw, vh = full.width(), full.width() / ar
        elif fit == "height":
            vw, vh = full.height() * ar, full.height()
        elif fit == "original":
            z = self.opt("zoom")
            vw, vh = W / z, H / z
        else:  # anpassa till skärm enligt CDisplayEx: krymp/förstora separat för bredd och höjd
            iw, ih = full.width(), full.height()
            c = []
            if (iw > W and self.opt("shrink_w")) or (iw < W and self.opt("grow_w")):
                c.append(W / iw)
            if (ih > H and self.opt("shrink_h")) or (ih < H and self.opt("grow_h")):
                c.append(H / ih)
            z = min(c) if c else 1.0
            vw, vh = W / z, H / z
        xs = _steps(full.width(), vw)
        ys = _steps(full.height(), vh)
        if self.rtl:
            xs = list(reversed(xs))
        return [QRectF(x, y, vw, vh) for y in ys for x in xs]

    def targets(self):
        """[(rektangel, är_ruta)] för aktuellt uppslag."""
        sp = self._spread(self.sp) if self.spreads else None
        if sp is None:
            return []
        full = QRectF(0, 0, sp[0].width(), sp[0].height())
        ps, _ = self.panels()
        if self.guided() and ps:
            W, H = full.width(), full.height()
            pages_w = sp[1][0].width()
            m = MARGIN * pages_w
            t = [(QRectF(r.x() - m, r.y() - m, r.width() + 2 * m, r.height() + 2 * m).intersected(full), True) for r in ps]
            if self.opt("overview"):
                t = [(full, False)] + t
            return t
        return [(v, False) for v in self._viewports(full)]

    # ---------- navigering ----------
    def goto_page(self, i, forward=True, animate=True):
        if not self.comic or not self.spreads:
            return
        i = max(0, min(i, len(self.comic.pages) - 1))
        self.goto_spread(self.sp_of.get(i, 0), forward, animate)

    def goto_spread(self, s, forward=True, animate=True):
        if not self.comic:
            return
        self.custom = None
        self.free = False
        self.at_end = False
        self.sp = max(0, min(s, len(self.spreads) - 1))
        self.page = self.spreads[self.sp][0]
        self.detector and self.detector.set_focus(self.page)
        self.state.set_page(self.comic.path, self.page)
        self._ensure_loaded()
        t = self.targets()
        _ps, ready = self.panels()
        self.pidx = 0 if forward or not t else len(t) - 1
        self.pending_entry = not ready and forward and self.guided()
        sp = self._spread(self.sp)
        if sp is not None:
            full = QRectF(0, 0, sp[0].width(), sp[0].height())
            if not animate or self.view.isEmpty():
                self.view = self.focus = full
            self._retarget(animate)
        self.changed.emit()
        self.update()

    def step(self, d):
        if not self.comic:
            return
        self.pending_entry = False
        t = self.targets()
        if self.custom is not None:  # efter dubbelklick: fortsätt från målet närmast den klickade rutan
            c = self.custom
            self.custom = None
            if t:
                self.pidx = min(range(len(t)), key=lambda i: (t[i][0].center() - c.center()).manhattanLength())
        if self.free:
            self.free = False
            self._retarget()
            return
        n = self.pidx + d
        if 0 <= n < len(t):
            self.pidx = n
            self._retarget()
            self.changed.emit()
        elif 0 <= self.sp + d < len(self.spreads):
            self.goto_spread(self.sp + d, forward=d > 0)
        elif d > 0:
            if self.at_end or not self.opt("auto_next_file"):
                self.at_end = False
                self.slideshow.stop()
                self.finished.emit()
            else:
                self.at_end = True
                self.flash("Slut på serien – tryck igen för nästa fil")
        else:
            self.flash("Första sidan")

    def first(self):
        self.goto_spread(0)

    def last(self):
        self.goto_spread(len(self.spreads) - 1)

    def page_step(self, d):
        if self.comic:
            self.goto_spread(self.sp + d, forward=d > 0)

    # ---------- geometri ----------
    def _target(self):
        sp = self._spread(self.sp) if self.spreads else None
        if sp is None:
            return None, None
        full = QRectF(0, 0, sp[0].width(), sp[0].height())
        if self.custom is not None:
            return self._fit_aspect(self.custom, full), self.custom
        t = self.targets()
        if not t:
            return full, full
        r, is_panel = t[max(0, min(self.pidx, len(t) - 1))]
        if is_panel:
            return self._fit_aspect(r, full), r
        return r, full

    def _fit_aspect(self, r, full):
        """Rutan i fönstrets proportioner, centrerad. Med svart runt rutan syns inga halva grannrutor."""
        ar = self.width() / self.area_h()
        w, h = r.width(), r.height()
        if w / max(h, 1e-6) < ar:
            w = h * ar
        else:
            h = w / ar
        x = r.center().x() - w / 2
        y = r.center().y() - h / 2
        if self.opt("dim") and r != full:
            return QRectF(x, y, w, h)
        x = (full.width() - w) / 2 if w >= full.width() else min(max(x, 0), full.width() - w)
        y = (full.height() - h) / 2 if h >= full.height() else min(max(y, 0), full.height() - h)
        return QRectF(x, y, w, h)

    def _retarget(self, animate=True):
        v, f = self._target()
        if v is None:
            return
        self.a0, self.f0 = QRectF(self.view), QRectF(self.focus)
        self.a1, self.f1 = v, f
        if animate and self.opt("anim") and not self.a0.isEmpty():
            self.animating = True
            self.anim.stop()
            self.anim.start()
        else:
            self.anim.stop()
            self.animating = False
            self.view, self.focus = v, f
            self.update()

    def _clamp_retarget(self, animate=True):
        t = self.targets()
        self.pidx = max(0, min(self.pidx, len(t) - 1)) if t else 0
        self._retarget(animate)

    def _tick(self, t):
        self.view = lerp_rect(self.a0, self.a1, t)
        self.focus = lerp_rect(self.f0, self.f1, t)
        self.update()

    def _anim_done(self):
        self.animating = False
        self.update()

    # ---------- bilder ----------
    def _ensure_loaded(self):
        want = []
        for ds in (0, 1, -1, 2):
            s = self.sp + ds
            if 0 <= s < len(self.spreads):
                want += self.spreads[s]
        opts = {"rotation": self.opt("rotation"), "auto": self.opt("auto_color"),
                "g": self.opt("gamma"), "vib": self.opt("vibrance")}
        for i in want:
            if i not in self.images and i not in self.loading:
                self.loading.add(i)
                self.pool.start(_Load(self.comic, i, self.sig, opts, self.gen))
        keep = set()
        for s in range(self.sp - KEEP_SPREADS, self.sp + KEEP_SPREADS + 1):
            if 0 <= s < len(self.spreads):
                keep.update(self.spreads[s])
        for k in [k for k in self.images if k not in keep]:
            del self.images[k]
        for s in [s for s in self.sp_cache if abs(s - self.sp) > KEEP_SPREADS]:
            del self.sp_cache[s]

    def _on_loaded(self, i, img, gen):
        if gen != self.gen or not self.comic:
            return
        self.loading.discard(i)
        if img.isNull():
            img = QImage(800, 1200, QImage.Format.Format_RGB32)
            img.fill(QColor(40, 40, 40))
        self.images[i] = img
        was_land = self._landscape(i)
        self.sizes[i] = (img.width(), img.height())
        if self.opt("double") and self._landscape(i) != was_land:
            self._layout(keep_page=True)  # liggande sida upptäckt: visa den ensam
            return
        if i in self.spreads[self.sp] and self._spread(self.sp) is not None:
            sp = self._spread(self.sp)
            full = QRectF(0, 0, sp[0].width(), sp[0].height())
            if self.view.isEmpty() or not self.animating:
                self.view = self.focus = full if self.view.isEmpty() else self.view
            t = self.targets()
            self.pidx = max(0, min(self.pidx, len(t) - 1)) if t else 0
            self._retarget(animate=not self.view.isEmpty())
            self.changed.emit()

    def _on_detected(self, i):
        if not self.comic or not self.spreads or i not in self.spreads[self.sp]:
            return
        ps, ready = self.panels()
        if not ready:
            return
        if self.pending_entry and ps and self.guided():
            self.pidx = 0
            self._retarget()
        else:
            self._clamp_retarget()
        self.pending_entry = False
        self.changed.emit()
        self.update()

    def _on_progress(self, done, total):
        self.progress = (done, total)
        if done == total or done % 10 == 0:
            self.update()

    def current_image(self):
        """Originalbytes + namn för aktuell sida (spara/kopiera)."""
        if not self.comic:
            return None, None
        return self.comic.read(self.page), Path(self.comic.pages[self.page]).name

    # ---------- rendering ----------
    def area_h(self):
        """Höjden som sidan visas i: miniatyrlist och reglage tar plats längst ner i stället för att täcka rutan."""
        h = self.height()
        if self.thumbbar.isVisible():
            h -= self.thumbbar.height()
        if self.slider.isVisible():
            h -= self.slider.height()
        return max(h, 1)

    def _scale(self):
        v = self.view
        return min(self.width() / max(v.width(), 1e-6), self.area_h() / max(v.height(), 1e-6))

    def _offset(self):
        s = self._scale()
        return ((self.width() - self.view.width() * s) / 2 - self.view.x() * s,
                (self.area_h() - self.view.height() * s) / 2 - self.view.y() * s)

    def _to_screen(self, r):
        s = self._scale()
        ox, oy = self._offset()
        return QRectF(ox + r.x() * s, oy + r.y() * s, r.width() * s, r.height() * s)

    def _to_page(self, pos):
        s = self._scale()
        ox, oy = self._offset()
        return QPointF((pos.x() - ox) / s, (pos.y() - oy) / s)

    def bg_color(self):
        sp = self._spread(self.sp) if self.comic and self.spreads else None
        if sp is not None:
            return sp[3]
        c = self.opt("bg")
        return QColor(12, 12, 12) if c == "auto" else QColor(c)

    def paintEvent(self, _):
        p = QPainter(self)
        bg = self.bg_color()
        p.fillRect(self.rect(), bg)
        sp = self._spread(self.sp) if self.comic and self.spreads else None
        if sp is not None and not self.view.isEmpty():
            img = sp[0]
            q = self.opt("quality")
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,
                            q == "best" or (q == "smooth" and not self.animating))
            full = QRectF(0, 0, img.width(), img.height())
            src = self.view.intersected(full)
            p.drawImage(self._to_screen(src), img, src)
            if self.opt("dim") and self.focus != full and not self.free:
                self._dim(p, self._to_screen(self.focus), bg)
            if self.mag_on or self.mag_hold:
                self._magnifier(p, img)
            if self.edit:
                self._paint_edit(p)
        elif self.comic:
            self._text(p, "Laddar…", center=True)
        self._overlays(p)
        self._hud(p)
        if self.show_help:
            self._text(p, self.help_text, center=True)

    def _dim(self, p, f, bg):
        c = QColor(bg)
        W, H = self.width(), self.height()
        p.fillRect(QRectF(0, 0, W, f.top()), c)
        p.fillRect(QRectF(0, f.bottom(), W, H - f.bottom()), c)
        p.fillRect(QRectF(0, f.top(), f.left(), f.height()), c)
        p.fillRect(QRectF(f.right(), f.top(), W - f.right(), f.height()), c)

    def _magnifier(self, p, img):
        r = self.opt("mag_size") / 2
        z = self.opt("mag_zoom")
        s = self._scale() * z
        c = self._to_page(self.mouse)
        src = QRectF(c.x() - r / s, c.y() - r / s, 2 * r / s, 2 * r / s)
        dst = QRectF(self.mouse.x() - r, self.mouse.y() - r, 2 * r, 2 * r)
        path = QPainterPath()
        path.addEllipse(dst)
        p.save()
        p.setClipPath(path)
        p.fillRect(dst, self.bg_color())
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        full = QRectF(0, 0, img.width(), img.height())
        vis = src.intersected(full)
        if not vis.isEmpty():
            k = dst.width() / src.width()
            p.drawImage(QRectF(dst.x() + (vis.x() - src.x()) * k, dst.y() + (vis.y() - src.y()) * k,
                               vis.width() * k, vis.height() * k), img, vis)
        p.restore()
        p.setPen(QPen(QColor(220, 220, 220), 2))
        p.drawEllipse(dst)

    def _overlays(self, p):
        if not self.comic:
            return
        n = len(self.comic.pages)
        W, H = self.width(), self.height()
        if self.opt("show_progress") and n > 1:
            frac = (self.spreads[self.sp][-1] + 1) / n if self.spreads else 0
            p.fillRect(QRectF(0, H - 4, W, 4), QColor(255, 255, 255, 40))
            x0 = W * (1 - frac) if self.rtl else 0
            p.fillRect(QRectF(x0, H - 4, W * frac, 4), QColor(90, 160, 255, 200))
        if self.opt("show_pagenum"):
            pages = self.spreads[self.sp] if self.spreads else (self.page,)
            s = f"{pages[0] + 1}" + (f"–{pages[-1] + 1}" if len(pages) > 1 else "") + f" / {n}"
            p.setFont(QFont("Segoe UI", 10))
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(s) + 16
            p.fillRect(QRectF(W - w - 8, H - fm.height() - 16, w, fm.height() + 6), QColor(0, 0, 0, 150))
            p.setPen(QColor(220, 220, 220))
            p.drawText(QPointF(W - w, H - 13 - fm.descent()), s)

    def _text(self, p, s, center=False, pos=None):
        p.setFont(QFont("Segoe UI", 12))
        fm = p.fontMetrics()
        lines = s.split("\n")
        w = max(fm.horizontalAdvance(l) for l in lines) + 24
        h = fm.height() * len(lines) + 16
        x, y = ((self.width() - w) / 2, (self.height() - h) / 2) if center else (pos or (12, 12))
        p.fillRect(QRectF(x, y, w, h), QColor(0, 0, 0, 200))
        p.setPen(QColor(235, 235, 235))
        for k, l in enumerate(lines):
            p.drawText(QPointF(x + 12, y + 8 + fm.ascent() + k * fm.height()), l)

    def status_parts(self):
        if not self.comic:
            return []
        ps, ready = self.panels()
        pages = self.spreads[self.sp] if self.spreads else (self.page,)
        n = len(self.comic.pages)
        parts = [self.comic.title,
                 f"sida {pages[0] + 1}" + (f"–{pages[-1] + 1}" if len(pages) > 1 else "") + f" av {n}"]
        t = self.targets()
        if not self.guided():
            parts.append("sidläge")
        elif not ready:
            parts.append("söker rutor…")
        elif ps:
            k = self.pidx - (1 if self.opt("overview") else 0)
            parts.append(f"ruta {k + 1}/{len(ps)}" if k >= 0 else f"helsida ({len(ps)} rutor)")
        elif len(t) > 1:
            parts.append(f"del {self.pidx + 1}/{len(t)}")
        parts.append("höger→vänster" if self.rtl else "vänster→höger")
        d, tot = self.progress
        if tot and d < tot:
            parts.append(f"detektering {d}/{tot}")
        if self.detector and not self.detector.ml_ok:
            parts.append("ML av (bara CV)")
        return parts

    def _hud(self, p):
        if not self.comic:
            self._text(p, self.msg or "Dra in en mapp, ett serie-arkiv, en PDF eller en bild hit\n"
                       "L = bläddra   Ctrl+O = öppna fil   Ctrl+L = senaste   F = helskärm   H = hjälp",
                       center=True)
            return
        if not (self.hud_always or self.hud_timer.isActive() or self.msg):
            return
        s = "  ·  ".join(self.status_parts())
        if self.msg:
            s += "\n" + self.msg
        self._text(p, s)

    def flash(self, msg=""):
        self.msg = msg
        self.hud_timer.start()
        QTimer.singleShot(2500, self._clear_msg)
        self.update()

    def _clear_msg(self):
        if not self.hud_timer.isActive():
            self.msg = ""
            self.update()

    # ---------- zoom ----------
    def zoom(self, f, at=None):
        if self.view.isEmpty():
            return
        at = at or QPointF(self.width() / 2, self.height() / 2)
        pt = self._to_page(at)
        w, h = self.view.width() / f, self.view.height() / f
        fx, fy = (pt.x() - self.view.x()) / self.view.width(), (pt.y() - self.view.y()) / self.view.height()
        self.view = QRectF(pt.x() - fx * w, pt.y() - fy * h, w, h)
        self.free = True
        self.anim.stop()
        self.animating = False
        self.update()

    def reset_zoom(self):
        self.free, self.custom = False, None
        self._retarget()

    # ---------- bildspel / förstoringsglas ----------
    def toggle_slideshow(self):
        if self.slideshow.isActive():
            self.slideshow.stop()
            self.flash("Bildspel av")
        elif self.comic:
            self.slideshow.start(int(self.opt("slideshow_ms")))
            how = "ruta för ruta" if self.opt("slideshow_mode") == "guided" and self.guided() else "sida för sida"
            self.flash(f"Bildspel: {self.opt('slideshow_ms')} ms per steg, {how}")
        self.changed.emit()

    def _slide(self):
        """Ett steg i bildspelet: nästa ruta (guidat läge) eller nästa sida; vid slutet ev. nästa fil."""
        if not self.comic:
            self.slideshow.stop()
        elif self.opt("slideshow_mode") == "pages" or not self.guided():
            if self.sp < len(self.spreads) - 1:
                self.page_step(1)
                return
        elif self.sp < len(self.spreads) - 1 or self.pidx < len(self.targets()) - 1:
            self.step(1)
            return
        if self.comic and self.opt("slideshow_next_file"):
            sib = self.comic.siblings()
            if self.comic.path in sib and sib.index(self.comic.path) + 1 < len(sib):
                self.sibling(1)
                self.slideshow.start(int(self.opt("slideshow_ms")))
                return
        self.slideshow.stop()
        self.flash("Bildspelet är slut")
        self.changed.emit()

    def toggle_magnifier(self):
        self.mag_on = not self.mag_on
        self.update()
        self.changed.emit()

    # ---------- miniatyrlist / reglage ----------
    def toggle_thumbbar(self):
        if self.thumbbar.isVisible():
            self.thumbbar.hide()
            self.setFocus()
        elif self.comic:
            self.thumbbar.set_comic(self.comic, self.rtl)
            self.thumbbar.show_at(self.page)
            self._place_overlays()
        self._clamp_retarget(animate=False)
        self.changed.emit()

    def toggle_slider(self):
        if self.slider.isVisible():
            self.slider.hide()
        elif self.comic:
            self.slider.show()
            self.slider.raise_()
        self._sync_overlays()
        self._clamp_retarget(animate=False)
        self.changed.emit()

    def _thumb_picked(self, i, close):
        self.goto_page(i)
        if close:
            self.thumbbar.hide()
            self._clamp_retarget(animate=False)
        self.setFocus()

    def _place_overlays(self):
        W, H = self.width(), self.height()
        y = H
        if self.slider.isVisible():
            y -= self.slider.height()
            self.slider.setGeometry(0, y, W, self.slider.height())
        self.thumbbar.setGeometry(0, y - self.thumbbar.height(), W, self.thumbbar.height())

    def _sync_overlays(self):
        if not self.comic:
            self.thumbbar.hide()
            self.slider.hide()
            self.thumbbar.set_comic(None, False)
            return
        if self.slider.isVisible():
            self.slider.sync(self.page, len(self.comic.pages), self.rtl)
        if self.thumbbar.isVisible() and self.thumbbar.comic is self.comic:
            self.thumbbar.select(self.page)
        self._place_overlays()

    # ---------- redigera rutor ----------
    def toggle_edit(self):
        """Redigeringsläge: hela uppslaget med numrerade rutor. Dra = ny ruta, högerklick/Delete = ta bort,
        Ctrl+Z = ångra. Rättelserna sparas per sida och samlas som träningsdata för modellen."""
        if not self.comic:
            return
        if self.opt("rotation"):
            self.flash("Rotera tillbaka till 0° för att redigera rutor")
            return
        self.edit = not self.edit
        self.edit_drag = None
        if self.edit:
            self.slideshow.stop()
            sp = self._spread(self.sp)
            self.custom = QRectF(0, 0, sp[0].width(), sp[0].height()) if sp else None
            self.free = False
            self._retarget(animate=False)
        else:
            self.custom = None
            self._clamp_retarget()
            self.flash("Rutorna sparade")
        self.changed.emit()
        self.update()

    def _edit_boxes(self, p):
        ps, _ = self._page_panels(p)
        return [dict(q) for q in ps]

    def _edit_store(self, p, boxes):
        name = self.comic.pages[p]
        self.edit_undo.append((p, self.user.get(name)))
        self.user.set(name, boxes)
        try:  # träningsdata: sidan som JPEG + rutorna
            import hashlib
            from PySide6.QtCore import QBuffer, QIODevice
            key = hashlib.sha1(f"{self.comic.path}|{name}".encode()).hexdigest()[:20]
            img = QImage.fromData(self.comic.read(p))
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "JPG", 92)
            save_training_example(bytes(buf.data()), boxes, key)
        except Exception:
            pass
        self.update()

    def _edit_page_at(self, pt):
        sp = self._spread(self.sp)
        if not sp:
            return None, None
        for r, p in zip(sp[1], sp[2]):
            if r.contains(pt):
                return p, r
        return None, None

    def edit_delete_at(self, pt):
        p, r = self._edit_page_at(pt)
        if p is None:
            return
        boxes = self._edit_boxes(p)
        nx, ny = (pt.x() - r.x()) / r.width(), (pt.y() - r.y()) / r.height()
        hit = [b for b in boxes if b["x"] <= nx <= b["x"] + b["w"] and b["y"] <= ny <= b["y"] + b["h"]]
        if hit:
            boxes.remove(min(hit, key=G.area))
            self._edit_store(p, boxes)

    def edit_delete_under_mouse(self):
        if self.edit:
            self.edit_delete_at(self._to_page(self.mouse))

    def edit_add(self, a, b):
        p, r = self._edit_page_at(QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2))
        if p is None:
            return
        x0, x1 = sorted(((a.x() - r.x()) / r.width(), (b.x() - r.x()) / r.width()))
        y0, y1 = sorted(((a.y() - r.y()) / r.height(), (b.y() - r.y()) / r.height()))
        x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)
        q = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
        if q["w"] < 0.03 or q["h"] < 0.03:
            return
        boxes = [b for b in self._edit_boxes(p) if G.inter(b, q) / G.area(b) < 0.8]  # ersätter rutor den täcker
        self._edit_store(p, boxes + [q])

    def edit_undo_last(self):
        if self.edit and self.edit_undo:
            p, old = self.edit_undo.pop()
            self.user.set(self.comic.pages[p], old)
            self.update()

    def edit_reset_page(self):
        """Tillbaka till automatisk detektering för sidorna i uppslaget."""
        if not self.edit:
            return
        for p in self.spreads[self.sp]:
            name = self.comic.pages[p]
            self.edit_undo.append((p, self.user.get(name)))
            self.user.set(name, None)
        self.update()

    def _paint_edit(self, p):
        ps, _ = self.panels()
        p.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        for k, r in enumerate(ps):
            sr = self._to_screen(r)
            p.setPen(QPen(QColor(255, 60, 60), 3))
            p.setBrush(QColor(255, 60, 60, 35))
            p.drawRect(sr)
            tag = QRectF(sr.x() + 4, sr.y() + 4, 34, 30)
            p.fillRect(tag, QColor(255, 60, 60))
            p.setPen(QColor(255, 255, 255))
            p.drawText(tag, Qt.AlignmentFlag.AlignCenter, str(k + 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.edit_drag:
            a, b = self.edit_drag
            p.setPen(QPen(QColor(90, 200, 255), 2, Qt.PenStyle.DashLine))
            p.drawRect(self._to_screen(QRectF(a, b).normalized()))
        self._text(p, "REDIGERA RUTOR  ·  dra = ny ruta  ·  högerklick/Delete = ta bort  ·  Ctrl+Z = ångra  ·  "
                      "Ctrl+R = automatiskt igen  ·  E = klar", pos=(12, self.area_h() - 48))

    # ---------- inmatning ----------
    def next_dir(self, key_right):
        return (-1 if self.rtl else 1) * (1 if key_right else -1)

    def toggle_rtl(self):
        if not self.comic:
            return
        self.rtl = not self.rtl
        self.state.set_rtl(self.comic.path, self.rtl)
        self.sp_cache.clear()
        self.flash("Läsriktning: " + ("höger→vänster (japansk)" if self.rtl else "vänster→höger"))
        self.goto_page(self.page, animate=False)

    def _hide_cursor(self):
        if self.window().isFullScreen() and self.opt("hide_cursor") and not (self.mag_on or self.mag_hold):
            self.setCursor(Qt.CursorShape.BlankCursor)

    def wheelEvent(self, e):
        if self.edit:
            return
        dy = e.angleDelta().y()
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.15 if dy > 0 else 1 / 1.15, e.position())
            return
        self.wheel_acc += dy
        if abs(self.wheel_acc) >= 120:
            self.step(-1 if self.wheel_acc > 0 else 1)
            self.wheel_acc = 0

    def mousePressEvent(self, e):
        b = e.button()
        if self.edit:
            if b == Qt.MouseButton.LeftButton:
                pt = self._to_page(e.position())
                self.edit_drag = (pt, pt)
            elif b == Qt.MouseButton.RightButton:
                self.edit_delete_at(self._to_page(e.position()))
            return
        if b == Qt.MouseButton.LeftButton:
            self.drag = (e.position(), QRectF(self.view), False)
        elif b == Qt.MouseButton.MiddleButton:
            self.mag_hold = True
            self.update()
        elif b == Qt.MouseButton.BackButton:
            self.sibling(-1)
        elif b == Qt.MouseButton.ForwardButton:
            self.sibling(1)

    def mouseMoveEvent(self, e):
        self.mouse = e.position()
        if self.edit:
            if self.edit_drag:
                self.edit_drag = (self.edit_drag[0], self._to_page(e.position()))
                self.update()
            return
        self.unsetCursor()
        self.cursor_timer.start()
        if self.drag and e.buttons() & Qt.MouseButton.LeftButton:
            start, v, moved = self.drag
            d = e.position() - start
            if moved or abs(d.x()) + abs(d.y()) > 6:
                s = self._scale()
                self.view = v.translated(-d.x() / s, -d.y() / s)
                self.free = True
                self.drag = (start, v, True)
        if self.drag or self.mag_on or self.mag_hold:
            self.update()

    def mouseReleaseEvent(self, e):
        b = e.button()
        if self.edit:
            if b == Qt.MouseButton.LeftButton and self.edit_drag:
                a, c = self.edit_drag
                self.edit_drag = None
                self.edit_add(a, c)
            return
        if b == Qt.MouseButton.LeftButton and self.drag and not self.drag[2]:
            pos = e.position()
            if self.comic and self.opt("show_progress") and pos.y() > self.height() - 14:
                frac = pos.x() / self.width()
                self.goto_page(int((1 - frac if self.rtl else frac) * len(self.comic.pages)))
            else:
                x = pos.x() / self.width()
                if x > 0.8:  # smala kantzoner så att dubbelklick på rutor i mitten fungerar
                    self.step(self.next_dir(True))
                elif x < 0.2:
                    self.step(self.next_dir(False))
                else:
                    self.hud_timer.start()
                    self.update()
        elif b == Qt.MouseButton.RightButton:
            self.contextMenu.emit(e.globalPosition())
        elif b == Qt.MouseButton.MiddleButton:
            self.mag_hold = False
            self.update()
        self.drag = None

    def mouseDoubleClickEvent(self, e):
        """Som Smart Comic Reader: dubbelklick på en ruta zoomar till den. Dubbelklick på inzoomad ruta = helsida."""
        if e.button() != Qt.MouseButton.LeftButton or self.edit:
            return
        sp = self._spread(self.sp) if self.comic and self.spreads else None
        if sp is None:
            return
        img = sp[0]
        pt = self._to_page(e.position())
        full = QRectF(0, 0, img.width(), img.height())
        if not full.contains(pt):
            return
        if not self.free and self.focus != full and self.focus.contains(pt):
            self.custom = full  # tillbaka till hela uppslaget
            self._retarget()
            return
        ps, _ = self.panels()
        hit = [r for r in ps if r.contains(pt)]
        if hit:
            r = min(hit, key=lambda q: q.width() * q.height())
            m = MARGIN * sp[1][0].width()
            r = QRectF(r.x() - m, r.y() - m, r.width() + 2 * m, r.height() + 2 * m).intersected(full)
        else:
            W, H = img.width(), img.height()
            g = img.convertToFormat(QImage.Format.Format_Grayscale8)
            arr = np.frombuffer(g.constBits(), np.uint8, g.bytesPerLine() * H).reshape(H, g.bytesPerLine())[:, :W]
            q = G.panel_at(arr, pt.x(), pt.y())
            if q is None:  # ingen ruta hittad: zooma till halva sidan runt punkten
                r = QRectF(pt.x() - W / 4, pt.y() - H / 4, W / 2, H / 2).intersected(full)
            else:
                m = MARGIN * W
                r = QRectF(q["x"] * W - m, q["y"] * H - m, q["w"] * W + 2 * m, q["h"] * H + 2 * m).intersected(full)
        self.free = False
        self.custom = r
        self._retarget()

    def resizeEvent(self, e):
        self._place_overlays()
        if self.comic and not self.free:
            self._clamp_retarget(animate=False)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self.open(urls[0].toLocalFile())
