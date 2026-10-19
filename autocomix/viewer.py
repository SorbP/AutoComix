"""The display area: pages/spreads, guided panel-by-panel zoom, fit modes, magnifier, slideshow.

Navigation goes through a list of "targets" per spread: panels (guided mode) or view windows by
the fit mode (screen/width/height/original size). Arrow/click/wheel steps through the targets and then to the next spread.
"""
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import (QEasingCurve, QObject, QPointF, QRectF, QRunnable, Qt, QThreadPool, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

from . import animation
from .i18n import tr
from . import geometry as G
from . import imaging
from .comic import IMAGE_EXT, Comic, PasswordNeeded
from .detector import Detector
from .overlays import PageSlider, ThumbBar
from .second import paint_frame
from .store import PanelCache, State, UserPanels, load_sidecar, save_training_example, training_counts

MARGIN = 0.012     # space around the panel, share of the page
SCROLL_OVERLAP = 0.1  # overlap when a page is shown in several steps (fit width/height/zoom)
KEEP_SPREADS = 3   # spreads before/after kept in memory

DEFAULTS = {
    "guided": True, "overview": False, "dim": True, "order_xy": False,  # order_xy: column beside a tall panel first
    "fit": "screen", "zoom": 1.0,
    "shrink_w": True, "grow_w": True, "shrink_h": True, "grow_h": True,  # CDisplayEx: over/under width/height
    "double": False, "cover_single": True, "shadow": True,
    "rotation": 0, "auto_color": False, "gamma": 1.0, "vibrance": 0.0,
    "bg": "#0c0c0c", "quality": "smooth", "anim": True, "anim_ms": 320,
    "slideshow_ms": 5000, "slideshow_mode": "guided", "slideshow_next_file": False, "slideshow_loop": False, "detect_large": "ask", "detect_batch": 100, "language": "auto", "auto_next_file": True, "history": True, "clear_history_on_exit": False,
    "sort": "natural",
    "esc_quit": "never", "hide_cursor": True,
    "show_pagenum": True, "show_progress": True, "mag_size": 320, "mag_zoom": 2.0,
    "mag_shape": "rect", "mag_aspect": 0.6, "mag_warp": 0.5,  # rect/square/circle flat, lens = round with distortion
    "anim_play": True, "anim_speed": 1.0, "slideshow_wait_anim": True,  # animated pages (GIF/WebP/APNG)
    "ui_scale": 1.0,                                   # size of text/lists in the display (and menus/dialogs)
    "distance_mode": False, "distance_scale": 3.0,     # distance mode: large page counter that hides when idle
    "distance_ui_scale": 1.5,                          # ...and the whole interface this much larger
    "counter_autohide": False, "counter_hide_ms": 1000,
    "ml_device": "auto",  # panel detection: auto/gpu = graphics card (DirectML) with the processor as fallback, cpu
    "auto_turn": "off", "auto_turn_gain": 1.3,  # turn a panel 90° (cw/ccw) when it gets this much larger
}
ANIM_SPEEDS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0)
TURNS = (("off", tr("Av")), ("cw", tr("Medurs (90°)")), ("ccw", tr("Moturs (90°)")))
MAG_SHAPES = (("rect", tr("Rektangel")), ("square", tr("Kvadrat")), ("circle", tr("Rund")), ("lens", tr("Lins (rund, förvrängd)")))


def lerp_rect(a, b, t):
    return QRectF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t,
                  a.width() + (b.width() - a.width()) * t, a.height() + (b.height() - a.height()) * t)


def rotate_box(p, rot):
    """Normalized panel after the page has been rotated rot degrees clockwise."""
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
    """Start positions for a window of size view over the length total, with overlap, the last one against the edge."""
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
    frames = Signal(int, object, int)  # page, (frames, delays ms), generation – sent before loaded


class _Load(QRunnable):
    def __init__(self, comic, i, sig, opts, gen):
        super().__init__()
        self.comic, self.i, self.sig, self.opts, self.gen = comic, i, sig, opts, gen

    def run(self):
        anim = None
        try:
            data = self.comic.read(self.i)
            anim = animation.decode(data)
            if anim:  # color/rotation on every frame; the first frame is "the page" (panel detection, thumbnails)
                anim = ([imaging.process(f, **self.opts) for f in anim[0]], anim[1])
                img = anim[0][0]
            else:
                img = imaging.process(QImage.fromData(data), **self.opts)
        except Exception:
            img, anim = QImage(), None
        try:
            if anim:
                self.sig.frames.emit(self.i, anim, self.gen)
            self.sig.loaded.emit(self.i, img, self.gen)
        except RuntimeError:  # the window was closed while the page was loading
            pass


class Viewer(QWidget):
    changed = Signal()                 # title/page/mode changed (for menus and window title)
    contextMenu = Signal(QPointF)      # right-click
    passwordNeeded = Signal(str)       # krypterat arkiv
    finished = Signal()                # end of the comic reached (for "next file")
    painted = Signal()                 # after every paint (the second screen follows)

    def __init__(self, state=None):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(320, 240)
        self.state = state or State()
        from . import ml_onnx
        ml_onnx.set_device(self.opt("ml_device"))
        self.fit_key = lambda: "fit"  # the second screen switches to the left/right key (second.fit_key)
        self.comic = self.detector = self.cache = None
        self.sidecar, self.rtl = {}, False
        self.images, self.sizes, self.loading = {}, {}, set()
        self.gen = 0
        self.spreads, self.sp_of, self.sp_cache = [], {}, {}
        self.sp = 0
        self.page = 0
        self.pidx = 0
        self.turn = self.turn0 = self.turn1 = 0.0  # screen rotation in degrees (auto_turn), animated
        self.sig = _Sig()
        self.sig.loaded.connect(self._on_loaded)
        self.sig.frames.connect(self._on_frames)
        self.anims = {}       # page -> {"f": frames, "d": delays, "k": current frame, "loops": loops, "due": time}
        self.anim_key = None  # (spread, animated pages) the clock was last started for
        self.frame_timer = QTimer(self, singleShot=True, timeout=self._next_frame)
        self.pool = QThreadPool.globalInstance()
        self.view = self.focus = QRectF()
        self.a0 = self.a1 = self.f0 = self.f1 = QRectF()
        self.animating = self.free = self.pending_entry = False
        self.custom = None
        self.resume_panel = self.resume_wait = None  # panel to resume at (saved at the last close)
        self.show_help, self.help_text = False, ""
        self.hud_always = False
        self.msg, self.progress = "", (0, 0)
        self.drag = None
        self.wheel_acc = 0
        self.at_end = False
        self.mag_on = self.mag_hold = False
        self.edit, self.edit_drag, self.edit_undo, self.edit_redo = False, None, [], []  # the steps = lists of (page, panels)
        self.edit_grab = None  # (page, index, edges, original panel, start point) during resize/move
        self.order_pick = None  # order mode: {"p": page, "seq": panel indexes in clicked order}
        self.user = None
        self.frozen = None  # (image, view window, focus, background) shown instead – the second screen's distribution
        self.mouse = QPointF()
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=self.opt("anim_ms"),
                                      easingCurve=QEasingCurve.Type.OutCubic)
        self.anim.valueChanged.connect(self._tick)
        self.anim.finished.connect(self._anim_done)
        self.hud_timer = QTimer(self, singleShot=True, interval=2200, timeout=self._clear_msg)
        self.slideshow = QTimer(self, timeout=self._slide)
        self.cursor_timer = QTimer(self, singleShot=True, interval=2000, timeout=self._hide_cursor)
        self.last_activity = time.monotonic()
        self.counter_timer = QTimer(self, singleShot=True, timeout=self.update)  # hides the counter after inactivity
        app = QApplication.instance()
        if app:  # keys go through menu actions and do not reach the widget: listen to the whole program
            app.installEventFilter(self)
        self.thumbbar = ThumbBar(self)
        self.thumbbar.picked.connect(self._thumb_picked)
        self.slider = PageSlider(self)
        self.slider.picked.connect(lambda i: self.goto_page(i))
        self.changed.connect(self._sync_overlays)

    # ---------- settings ----------
    def opt(self, k):
        return self.state.setting(k, DEFAULTS.get(k))

    def fit(self):
        """Fit for the screen the main window is shown on ('main' only applies to the second screen)."""
        f = self.opt(self.fit_key()) or "screen"
        return "screen" if f == "main" else f

    def refit(self):
        """The fit may have changed (mode/screen): recompute the targets."""
        if self.comic:
            self.free, self.custom = False, None
            self._clamp_retarget(animate=False)
        self.update()

    def set_opt(self, k, v):
        self.state.set_setting(k, v)
        if k in ("rotation", "auto_color", "gamma", "vibrance"):
            self.reload_images()
        elif k in ("double", "cover_single"):
            self._layout(keep_page=True)
        elif k == "shadow":
            self.sp_cache.clear()
            self.goto_page(self.page, animate=False)
        elif k == "ml_device":
            from . import ml_onnx
            ml_onnx.set_device(v)  # the next page detected uses the new choice
        elif k == "anim_ms":
            self.anim.setDuration(v)
        elif k == "slideshow_ms" and self.slideshow.isActive():
            self.slideshow.start(int(v))
        elif k == "sort" and self.comic:  # reopen in the new order, stay on the same image
            name = self.comic.pages[self.page] if 0 <= self.page < len(self.comic.pages) else None
            if self.open(self.comic.path) is not False and name in self.comic.pages:
                self.goto_page(self.comic.pages.index(name), animate=False)
        elif self.comic:
            self.free, self.custom = False, None
            self._clamp_retarget(animate=False)
        self.changed.emit()
        self.update()

    # ---------- serie ----------
    def open(self, path, password=None):
        path = Path(path)
        first = None
        if path.is_file() and path.suffix.lower() in IMAGE_EXT:  # single image: open the folder and start at that image
            path, first = path.parent, path.name
        try:
            comic = self._make_comic(path, password)
        except PasswordNeeded:
            self.passwordNeeded.emit(str(path))
            return False
        except Exception as e:
            self.flash(tr("Kunde inte öppna: {err}").format(err=e))
            return False
        self.close_comic()
        self.comic = comic
        self.cache = PanelCache(path)
        self.user = UserPanels(path)
        self.sidecar = load_sidecar(path)
        self.rtl = self.state.rtl(path, comic.rtl_hint())
        saved = self.state.comic(path)
        start = min(saved.get("page", 0), len(comic.pages) - 1)
        self.resume_panel = saved.get("panel") if not first else None
        if first:
            start = next((i for i, n in enumerate(comic.pages) if Path(n).name == first), start)
        if self.opt("history"):
            self.state.add_history(path, len(comic.pages))
        self.detector = Detector(comic, self.cache)
        self.detector.pageDone.connect(self._on_detected)
        self.detector.progress.connect(self._on_progress)
        self.detector.set_focus(start)
        if self._scan_in_batches(comic):
            self.detector.set_batch(self.opt("detect_batch"))
        self.detector.start()
        self._layout()
        self.goto_page(start, forward=True, animate=False)
        self.flash(f"{comic.title}  (" + tr("{n} sidor").format(n=len(comic.pages)) + ")")
        self.changed.emit()
        return True

    def _make_comic(self, path, password):
        """rar/7z are extracted to a temp folder, which can take time: do it in a thread and show the progress."""
        if path.is_dir() or path.suffix.lower() not in (".rar", ".cbr", ".7z", ".cb7"):
            return Comic(path, password=password, sort=self.opt("sort"))
        import threading
        import time
        box = {"pct": 0}

        def work():
            try:
                box["c"] = Comic(path, password=password, sort=self.opt("sort"),
                                 progress=lambda pct: box.__setitem__("pct", pct))
            except BaseException as e:
                box["e"] = e
        th = threading.Thread(target=work, daemon=True)
        th.start()
        t0, dlg = time.monotonic(), None
        while th.is_alive():
            if dlg is None and time.monotonic() - t0 > 0.4:  # fast archives: no dialog that flashes by
                dlg = QProgressDialog(tr("Packar upp {name}…").format(name=path.name), None, 0, 100, self.window())
                dlg.setWindowTitle("AutoComix")
                dlg.setWindowModality(Qt.WindowModality.WindowModal)
                dlg.setMinimumDuration(0)
                dlg.show()
            if dlg:
                dlg.setValue(box["pct"])
            QApplication.processEvents()
            th.join(0.03)
        if dlg:
            dlg.close()
        if "e" in box:
            raise box["e"]
        return box["c"]

    def close_comic(self):
        self.slideshow.stop()
        if self.detector:
            self.detector.stop()
            self.detector = None
        if self.comic:
            self.state.set_page(self.comic.path, self.page, self.pidx)
            self.state.save()
            self.comic.close()
        self.comic = None
        self.frozen = None
        self._anim_clear()
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
            self.flash(tr("Ingen fler serie i mappen"))

    def reload_images(self):
        """Image settings changed (rotation/color): reload the pages, keep the position."""
        if not self.comic:
            return
        self.gen += 1
        self._anim_clear()
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
        """Splits the pages into spreads. Landscape pages and (optionally) the cover are shown alone."""
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
        """(image, page rectangles in display order, pages in display order) or None if not loaded."""
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
        """(panels normalized for the page, ready?)."""
        name = self.comic.pages[i]
        sc = self.sidecar.get(Path(name).stem.lower())
        up = self.user.get(name) if self.user else None
        xy = self.opt("order_xy")
        if up is not None:  # custom panels: only the reading order is computed (or set in order mode)
            ps = G.order(up, self.rtl, xy) if up else []
        elif sc is not None:
            ps = G.finalize(sc, self.rtl, xy)
        else:
            c = self.cache.get(name)
            if c is None:
                return [], False
            ps = G.finalize(G.merge(c["cv"], c["ml"]), self.rtl, xy)
        rot = self.opt("rotation")
        return [rotate_box(p, rot) for p in ps], True

    def panels(self, s=None):
        """(panels as QRectF in the spread's pixels in reading order, ready?)."""
        s = self.sp if s is None else s
        sp = self._spread(s)
        if sp is None:
            return [], False
        _img, rects, order, _bg = sp
        out, ready = [], True
        for p in self.spreads[s]:  # reading order = page order
            ps, ok = self._page_panels(p)
            ready &= ok
            r = rects[order.index(p)]
            out += [QRectF(r.x() + q["x"] * r.width(), r.y() + q["y"] * r.height(), q["w"] * r.width(), q["h"] * r.height())
                    for q in ps]
        if ready and len(self.spreads[s]) > 1 and any(not self._page_panels(p)[0] for p in self.spreads[s]):
            # one of the pages has no panels (whole page): show it as its own "panel" in reading order
            out = []
            for p in self.spreads[s]:
                ps, _ = self._page_panels(p)
                r = rects[order.index(p)]
                out += [QRectF(r.x() + q["x"] * r.width(), r.y() + q["y"] * r.height(), q["w"] * r.width(), q["h"] * r.height())
                        for q in ps] or [QRectF(r)]
        return out, ready

    def guided(self):
        return self.opt("guided")

    # ---------- targets ----------
    def _viewports(self, full):
        """View windows by the fit mode, in reading order."""
        W, H = max(self.width(), 1), self.area_h()
        ar = W / H
        fit = self.fit()
        if fit == "width":
            vw, vh = full.width(), full.width() / ar
        elif fit == "height":
            vw, vh = full.height() * ar, full.height()
        elif fit == "original":
            z = self.opt("zoom")
            vw, vh = W / z, H / z
        else:  # fit to screen like CDisplayEx: shrink/enlarge separately for width and height
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
        """[(rectangle, is_panel)] for the current spread."""
        sp = self._spread(self.sp) if self.spreads else None
        if sp is None:
            return []
        full = QRectF(0, 0, sp[0].width(), sp[0].height())
        ps, _ = self.panels()
        if self.guided() and ps:
            W, H = full.width(), full.height()
            pages_w = sp[1][0].width()
            m = MARGIN * pages_w
            t = []
            for k, r in enumerate(ps):  # one screen per panel: the whole panel is visible, as large as the window allows
                r = QRectF(r.x() - m, r.y() - m, r.width() + 2 * m, r.height() + 2 * m).intersected(full)
                t.append((r, True, k, r))
            if self.opt("overview"):
                t = [(full, False, -1, full)] + t
            return t
        return [(v, False, -1, full) for v in self._viewports(full)]

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
        self.order_pick = None
        self.sp = max(0, min(s, len(self.spreads) - 1))
        self.page = self.spreads[self.sp][0]
        self.detector and self.detector.set_focus(self.page)
        self.state.set_page(self.comic.path, self.page)
        self._ensure_loaded()
        t = self.targets()
        _ps, ready = self.panels()
        self.pidx = 0 if forward or not t else len(t) - 1
        rp, self.resume_panel = self.resume_panel, None
        self.resume_wait = None
        if rp is not None:
            if ready and t:
                self.pidx = max(0, min(int(rp), len(t) - 1))
            else:
                self.resume_wait = rp  # image or panels not ready yet: jump there when they are
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
        self.resume_wait = None
        t = self.targets()
        if self.custom is not None:  # after a double-click: continue from the target nearest the clicked panel
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
                self.flash(tr("Slut på serien – tryck igen för nästa fil"))
        else:
            self.flash(tr("Första sidan"))

    def first(self):
        self.goto_spread(0)

    def last(self):
        self.goto_spread(len(self.spreads) - 1)

    def page_step(self, d):
        if self.comic:
            self.goto_spread(self.sp + d, forward=d > 0)

    # ---------- geometri ----------
    def _target(self):
        self.tgt_turn = 0.0
        sp = self._spread(self.sp) if self.spreads else None
        if sp is None:
            return None, None
        full = QRectF(0, 0, sp[0].width(), sp[0].height())
        if self.custom is not None:
            self.tgt_turn = self._turn_for(self.custom, full)
            return self._fit_aspect(self.custom, full, self.tgt_turn), self.custom
        t = self.targets()
        if not t:
            return full, full
        r, is_panel, _k, panel = t[max(0, min(self.pidx, len(t) - 1))]
        if is_panel:
            self.tgt_turn = self._turn_for(r, full)
            return self._fit_aspect(r, full, self.tgt_turn), panel.intersected(r)
        return r, full

    def _turn_for(self, r, full):
        """Degrees to turn the picture for the panel r: like Smart Comic Reader, a panel that fills the screen much
        better turned 90° (a wide panel on a portrait screen, a tall one on a landscape screen) is turned."""
        mode = self.opt("auto_turn")
        if mode not in ("cw", "ccw") or self.edit or r == full or r.isEmpty():
            return 0.0
        W, H = self.width(), self.area_h()
        s0 = min(W / r.width(), H / r.height())
        s1 = min(W / r.height(), H / r.width())
        return (90.0 if mode == "cw" else -90.0) if s1 > s0 * float(self.opt("auto_turn_gain")) else 0.0

    def _dims(self, turn=None):
        """The window's size seen from the turned picture (width and height swap at 90°, mixed while turning)."""
        k = abs(self.turn if turn is None else turn) / 90.0
        W, H = self.width(), self.area_h()
        return W + (H - W) * k, H + (W - H) * k

    def _fit_aspect(self, r, full, turn=0.0):
        """The panel in the window's proportions, centered. With black around the panel no half neighbour panels show."""
        W, H = self._dims(turn)
        ar = W / H
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
        self.turn0 = self.turn
        self.turn1 = self.tgt_turn
        if animate and self.opt("anim") and not self.a0.isEmpty():
            self.animating = True
            self.anim.stop()
            self.anim.start()
        else:
            self.anim.stop()
            self.animating = False
            self.view, self.focus = v, f
            self.turn = self.turn1
            self.update()

    def _clamp_retarget(self, animate=True):
        t = self.targets()
        self.pidx = max(0, min(self.pidx, len(t) - 1)) if t else 0
        self._retarget(animate)

    def _tick(self, t):
        self.view = lerp_rect(self.a0, self.a1, t)
        self.focus = lerp_rect(self.f0, self.f1, t)
        self.turn = self.turn0 + (self.turn1 - self.turn0) * t
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
        for k in [k for k in self.anims if k not in want]:  # all frames = a lot of memory: only the nearest spreads
            del self.anims[k]
            self.images.pop(k, None)
            for s in [s for s in self.sp_cache if k in self.spreads[s]]:
                del self.sp_cache[s]
        for k in [k for k in self.images if k not in keep]:
            del self.images[k]
        for s in [s for s in self.sp_cache if abs(s - self.sp) > KEEP_SPREADS]:
            del self.sp_cache[s]

    def _on_frames(self, i, fd, gen):
        if gen == self.gen and self.comic:
            self.anims[i] = {"f": fd[0], "d": fd[1], "k": 0, "loops": 0, "due": None}

    # ---------- animated pages ----------
    def _anim_clear(self):
        self.frame_timer.stop()
        self.anims.clear()
        self.anim_key = None

    def anim_pages(self):
        """Animated pages in the spread shown now."""
        if not self.comic or not self.spreads or self.sp >= len(self.spreads):
            return []
        return [p for p in self.spreads[self.sp] if p in self.anims]

    def _set_frame(self, p):
        a = self.anims[p]
        f = a["f"][a["k"]]
        if self.images.get(p) is not f:
            self.images[p] = f
            self.sp_cache.pop(self.sp_of.get(p), None)  # single page: no copy; a double page is put together again

    def _anim_sync(self):
        """On every paint: new spread -> the animation restarts from the first frame; the clock only runs for what is visible."""
        vis = self.anim_pages()
        key = (self.sp, tuple(vis))
        if key != self.anim_key:
            self.anim_key = key
            self.frame_timer.stop()
            for p in vis:
                self.anims[p].update(k=0, loops=0, due=None)
                self._set_frame(p)
        if vis and self.opt("anim_play") and not self.frame_timer.isActive():
            self._anim_schedule(vis)

    def _anim_speed(self):
        return max(0.1, float(self.opt("anim_speed")))

    def _anim_schedule(self, vis):
        now, sp = time.monotonic(), self._anim_speed()
        for p in vis:
            a = self.anims[p]
            if a["due"] is None or a["due"] < now - 1.0:  # start, or the clock has stood still (long paint/pause)
                a["due"] = now + a["d"][a["k"]] / 1000 / sp
        nxt = min(self.anims[p]["due"] for p in vis)
        self.frame_timer.start(max(1, int((nxt - now) * 1000)))

    def _next_frame(self):
        vis = self.anim_pages()
        if not vis or not self.opt("anim_play"):
            return
        now, sp = time.monotonic(), self._anim_speed()
        for p in vis:
            a = self.anims[p]
            if a["due"] is None:
                continue
            n = 0
            while a["due"] <= now and n < len(a["f"]):  # skips frames if the computer fell behind
                a["k"] = (a["k"] + 1) % len(a["f"])
                a["loops"] += a["k"] == 0
                a["due"] += a["d"][a["k"]] / 1000 / sp
                n += 1
            if n:
                self._set_frame(p)
        self.update()
        self._anim_schedule(vis)

    def toggle_anim(self):
        play = not self.opt("anim_play")
        self.set_opt("anim_play", play)
        self.frame_timer.stop()
        for p in self.anim_pages():
            self.anims[p]["due"] = None
        self.flash(tr("Animation: spelar") if play else tr("Animation: pausad"))
        self.update()
        self.changed.emit()

    def anim_step(self, d):
        """En bildruta fram/bak (pausar)."""
        vis = self.anim_pages()
        if not vis:
            self.flash(tr("Ingen animation på sidan"))
            return
        if self.opt("anim_play"):
            self.set_opt("anim_play", False)
            self.frame_timer.stop()
        for p in vis:
            a = self.anims[p]
            a["k"], a["due"] = (a["k"] + d) % len(a["f"]), None
            self._set_frame(p)
        a = self.anims[vis[0]]
        self.flash(tr("Bildruta {k}/{n} (pausad)").format(k=a['k'] + 1, n=len(a['f'])))
        self.update()
        self.changed.emit()

    def anim_speed_step(self, d):
        cur = self._anim_speed()
        i = min(range(len(ANIM_SPEEDS)), key=lambda j: abs(ANIM_SPEEDS[j] - cur))
        self.set_anim_speed(ANIM_SPEEDS[max(0, min(len(ANIM_SPEEDS) - 1, i + d))])

    def set_anim_speed(self, v):
        self.set_opt("anim_speed", v)
        for p in self.anim_pages():
            self.anims[p]["due"] = None
        self.frame_timer.stop()
        self.flash(tr("Animationshastighet {x}x").format(x=f"{v:g}"))
        self.update()
        self.changed.emit()

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
            self._layout(keep_page=True)  # landscape page detected: show it alone
            return
        if i in self.spreads[self.sp] and self._spread(self.sp) is not None:
            sp = self._spread(self.sp)
            full = QRectF(0, 0, sp[0].width(), sp[0].height())
            if self.view.isEmpty() or not self.animating:
                self.view = self.focus = full if self.view.isEmpty() else self.view
            t = self.targets()
            if self.resume_wait is not None and t and self.panels()[1]:
                self.pidx, self.resume_wait = int(self.resume_wait), None
            self.pidx = max(0, min(self.pidx, len(t) - 1)) if t else 0
            self._retarget(animate=not self.view.isEmpty())
            self.changed.emit()

    def _on_detected(self, i):
        if not self.comic or not self.spreads or i not in self.spreads[self.sp]:
            return
        ps, ready = self.panels()
        if not ready:
            return
        if self.resume_wait is not None and ps and self.guided():
            t = self.targets()
            self.pidx = max(0, min(int(self.resume_wait), len(t) - 1)) if t else 0
            self._retarget()
        elif self.pending_entry and ps and self.guided():
            self.pidx = 0
            self._retarget()
        else:
            self._clamp_retarget()
        self.resume_wait = None
        self.pending_entry = False
        self.changed.emit()
        self.update()

    def _on_progress(self, done, total):
        self.progress = (done, total)
        self.update()

    def current_image(self):
        """Original bytes + name for the current page (save/copy)."""
        if not self.comic:
            return None, None
        return self.comic.read(self.page), Path(self.comic.pages[self.page]).name

    # ---------- rendering ----------
    def area_h(self):
        """The height the page is shown in: the thumbnail bar and slider take space at the bottom instead of covering the panel."""
        h = self.height()
        if self.thumbbar.isVisible():
            h -= self.thumbbar.height()
        if self.slider.isVisible():
            h -= self.slider.height()
        return max(h, 1)

    def _scale(self):
        v = self.view
        W, H = self._dims()
        return min(W / max(v.width(), 1e-6), H / max(v.height(), 1e-6))

    def _offset(self):
        """Offset in the turned frame (which is the screen when nothing is turned)."""
        s = self._scale()
        W, H = self._dims()
        return ((W - self.view.width() * s) / 2 - self.view.x() * s,
                (H - self.view.height() * s) / 2 - self.view.y() * s)

    def _frame_xf(self):
        """Turned frame -> screen: the frame's center on the screen's center, turned self.turn degrees."""
        W, H = self._dims()
        return (QTransform().translate(self.width() / 2, self.area_h() / 2).rotate(self.turn)
                .translate(-W / 2, -H / 2))

    def _to_screen(self, r):
        s = self._scale()
        ox, oy = self._offset()
        return QRectF(ox + r.x() * s, oy + r.y() * s, r.width() * s, r.height() * s)

    def _to_page(self, pos):
        if self.turn:
            pos = self._frame_xf().inverted()[0].map(QPointF(pos))
        s = self._scale()
        ox, oy = self._offset()
        return QPointF((pos.x() - ox) / s, (pos.y() - oy) / s)

    def bg_color(self):
        sp = self._spread(self.sp) if self.comic and self.spreads else None
        if sp is not None:
            return sp[3]
        c = self.opt("bg")
        return QColor(12, 12, 12) if c == "auto" else QColor(c)

    def frame(self, final=False):
        """(image, view window, focus, background) shown now, or where the animation is heading (final)."""
        sp = self._spread(self.sp) if self.comic and self.spreads else None
        if sp is None or self.view.isEmpty():
            return None
        v, f = (self.a1, self.f1) if final and self.animating else (self.view, self.focus)
        return sp[0], QRectF(v), QRectF(f), sp[3]

    def paintEvent(self, _):
        self._paint()
        self.painted.emit()

    def _paint(self):
        if self.anims:
            self._anim_sync()
        p = QPainter(self)
        bg = self.bg_color()
        p.fillRect(self.rect(), bg)
        sp = self._spread(self.sp) if self.comic and self.spreads else None
        if self.frozen is not None and self.comic:  # the current image is shown on the second screen: keep the previous one here
            q = self.opt("quality")
            paint_frame(p, self.width(), self.area_h(), self.frozen, self.opt("dim"), q in ("best", "smooth"))
        elif sp is not None and not self.view.isEmpty():
            img = sp[0]
            q = self.opt("quality")
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,
                            q == "best" or (q == "smooth" and not self.animating))
            full = QRectF(0, 0, img.width(), img.height())
            src = self.view.intersected(full)
            p.save()
            if self.turn:
                p.setTransform(self._frame_xf())
            p.drawImage(self._to_screen(src), img, src)
            if self.opt("dim") and self.focus != full and not self.free:
                self._dim(p, self._to_screen(self.focus), bg)
            p.restore()
            if self.mag_on or self.mag_hold:
                self._magnifier(p, img)
            if self.edit:
                self._paint_edit(p)
        elif self.comic:
            self._text(p, tr("Laddar…"), center=True)
        self._overlays(p)
        self._hud(p)
        if self.show_help:
            self._text(p, self.help_text, center=True)

    def _dim(self, p, f, bg):
        c = QColor(bg)
        L = self.width() + self.height()  # reaches past the screen also when the frame is turned
        p.fillRect(QRectF(-L, -L, 3 * L, f.top() + L), c)
        p.fillRect(QRectF(-L, f.bottom(), 3 * L, 2 * L - f.bottom()), c)
        p.fillRect(QRectF(-L, f.top(), f.left() + L, f.height()), c)
        p.fillRect(QRectF(f.right(), f.top(), 2 * L - f.right(), f.height()), c)

    def mag_box(self):
        """The glass's rectangle on the screen (centered on the mouse) by shape and size."""
        w = float(self.opt("mag_size")) * self.ui_scale()
        h = w * float(self.opt("mag_aspect")) if self.opt("mag_shape") == "rect" else w
        return QRectF(self.mouse.x() - w / 2, self.mouse.y() - h / 2, w, h)

    def _magnifier(self, p, img):
        shape = self.opt("mag_shape")
        dst = self.mag_box()
        s = self._scale() * float(self.opt("mag_zoom"))
        c = self._to_page(self.mouse)
        quarter = round(self.turn / 90) % 2  # turned picture: render the glass turned back, then turn it
        dw, dh = (dst.height(), dst.width()) if quarter else (dst.width(), dst.height())
        src = QRectF(c.x() - dw / 2 / s, c.y() - dh / 2 / s, dw / s, dh / s)
        # render the magnified region to its own image (the same for all shapes)
        out = QImage(max(1, int(dw)), max(1, int(dh)), QImage.Format.Format_RGB32)
        out.fill(self.bg_color())
        q = QPainter(out)
        q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        full = QRectF(0, 0, img.width(), img.height())
        vis = src.intersected(full)
        if not vis.isEmpty():
            k = out.width() / src.width()
            q.drawImage(QRectF((vis.x() - src.x()) * k, (vis.y() - src.y()) * k, vis.width() * k, vis.height() * k),
                        img, vis)
        q.end()
        if self.turn:
            out = out.transformed(QTransform().rotate(round(self.turn / 90) * 90))
        if shape == "lens":
            out = self._lens_warp(out)
        path = QPainterPath()
        if shape in ("circle", "lens"):
            path.addEllipse(dst)
        else:
            path.addRect(dst)
        p.save()
        p.setClipPath(path)
        p.drawImage(dst.topLeft(), out)
        p.restore()
        p.setPen(QPen(QColor(220, 220, 220), max(1, round(2 * self.ui_scale()))))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    _warp_maps = {}

    def _lens_warp(self, img):
        """Fisheye: the center is magnified more, the edge is compressed (like a real magnifying glass)."""
        import cv2
        w, h = img.width(), img.height()
        g = min(0.8, max(0.0, float(self.opt("mag_warp"))) * 0.6)  # the center is magnified 1/(1-g) extra
        key = (w, h, round(g, 3))
        maps = Viewer._warp_maps.get(key)
        if maps is None:
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            cx, cy, rad = (w - 1) / 2, (h - 1) / 2, min(w, h) / 2
            dx, dy = (xx - cx) / rad, (yy - cy) / rad
            r = np.sqrt(dx * dx + dy * dy)
            # source radius = r·(1 − g(1 − r²)): soft bulge, no point in the center, the edge meets the surroundings
            f = np.where(r < 1, 1 - g * (1 - r * r), 1.0).astype(np.float32)
            maps = (cx + dx * f * rad, cy + dy * f * rad)
            if len(Viewer._warp_maps) > 8:
                Viewer._warp_maps.clear()
            Viewer._warp_maps[key] = maps
        a = imaging.to_rgb(img)
        return imaging.from_rgb(cv2.remap(a, maps[0], maps[1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE))

    def set_mag_shape(self, shape):
        self.set_opt("mag_shape", shape)
        if not (self.mag_on or self.mag_hold):
            self.mag_on = True
        self.flash(tr("Förstoringsglas: {shape}").format(shape=dict(MAG_SHAPES)[shape]))
        self.update()
        self.changed.emit()

    def mag_resize(self, f):
        val = max(80, min(1600, round(float(self.opt("mag_size")) * f)))
        self.set_opt("mag_size", val)
        self.flash(tr("Förstoringsglas {px} px").format(px=val))
        self.update()

    def mag_zoom_step(self, f):
        val = max(1.25, min(8.0, round(float(self.opt("mag_zoom")) * f * 4) / 4))
        self.set_opt("mag_zoom", val)
        self.flash(tr("Förstoring {x}×").format(x=f"{val:g}"))
        self.update()

    # ---------- size / distance mode ----------
    ACTIVITY = None

    def eventFilter(self, obj, e):
        if Viewer.ACTIVITY is None:
            from PySide6.QtCore import QEvent
            T = QEvent.Type
            Viewer.ACTIVITY = {T.KeyPress, T.MouseMove, T.MouseButtonPress, T.Wheel}
        if e.type() in Viewer.ACTIVITY:
            self.poke()
        return False

    def poke(self):
        """Activity (key, mouse, wheel): show the counter again and restart the countdown to hiding it."""
        was = self.counter_visible()
        self.last_activity = time.monotonic()
        if self.counter_autohides():
            self.counter_timer.start(int(self.opt("counter_hide_ms")) + 20)
            if not was:
                self.update()

    def base_ui_scale(self):
        return max(0.5, min(4.0, float(self.opt("ui_scale"))))

    def ui_scale(self):
        """The interface size right now: the setting, and in distance mode enlarged further."""
        k = float(self.opt("distance_ui_scale")) if self.opt("distance_mode") else 1.0
        return max(0.5, min(8.0, self.base_ui_scale() * k))

    def font(self, pt, bold=False):
        return QFont("Segoe UI", max(6, round(pt * self.ui_scale())),
                     QFont.Weight.Bold if bold else QFont.Weight.Normal)

    def counter_autohides(self):
        return bool(self.opt("distance_mode") or self.opt("counter_autohide"))

    def counter_visible(self):
        if not self.counter_autohides():
            return True
        return (time.monotonic() - self.last_activity) * 1000 < int(self.opt("counter_hide_ms"))

    def toggle_distance(self):
        on = not self.opt("distance_mode")
        self.set_opt("distance_mode", on)
        self.poke()
        self.flash(tr("Avståndsläge: stor sidräknare, döljs efter {s} s utan aktivitet").format(
            s=f"{int(self.opt('counter_hide_ms')) / 1000:g}") if on else tr("Avståndsläge av"))
        self.changed.emit()

    def _overlays(self, p):
        if not self.comic:
            return
        n = len(self.comic.pages)
        W, H = self.width(), self.height()
        u = self.ui_scale()
        bar = max(2, round(4 * u))
        if self.opt("show_progress") and n > 1:
            frac = (self.spreads[self.sp][-1] + 1) / n if self.spreads else 0
            p.fillRect(QRectF(0, H - bar, W, bar), QColor(255, 255, 255, 40))
            x0 = W * (1 - frac) if self.rtl else 0
            p.fillRect(QRectF(x0, H - bar, W * frac, bar), QColor(90, 160, 255, 200))
        d, tot = self.progress
        if tot and d < tot:  # panel detection for the whole comic in the background: thin orange bar above the reading progress
            p.fillRect(QRectF(0, H - bar - max(2, bar // 2), W * d / tot, max(2, bar // 2)), QColor(255, 170, 60, 220))
        if self.opt("show_pagenum") and not self.edit and self.counter_visible():
            s = self.counter_text()
            k = self.base_ui_scale() * float(self.opt("distance_scale")) if self.opt("distance_mode") else u
            p.setFont(QFont("Segoe UI", max(6, round(10 * k)),
                            QFont.Weight.DemiBold if self.opt("distance_mode") else QFont.Weight.Normal))
            fm = p.fontMetrics()
            pad, edge = round(8 * k), round(8 * k) + bar
            w, h = fm.horizontalAdvance(s) + 2 * pad, fm.height() + round(6 * k)
            r = QRectF(W - w - edge, H - h - edge, w, h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 170 if self.opt("distance_mode") else 150))
            p.drawRoundedRect(r, h * 0.2, h * 0.2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QColor(235, 235, 235))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, s)

    def _text(self, p, s, center=False, pos=None):
        p.setFont(self.font(12))
        fm = p.fontMetrics()
        u = self.ui_scale()
        lines = s.split("\n")
        w = max(fm.horizontalAdvance(l) for l in lines) + 24 * u
        h = fm.height() * len(lines) + 16 * u
        x, y = ((self.width() - w) / 2, (self.height() - h) / 2) if center else (pos or (12, 12))
        p.fillRect(QRectF(x, y, w, h), QColor(0, 0, 0, 200))
        p.setPen(QColor(235, 235, 235))
        for k, l in enumerate(lines):
            p.drawText(QPointF(x + 12 * u, y + 8 * u + fm.ascent() + k * fm.height()), l)

    def status_parts(self):
        if not self.comic:
            return []
        ps, ready = self.panels()
        pages = self.spreads[self.sp] if self.spreads else (self.page,)
        n = len(self.comic.pages)
        parts = [self.comic.title,
                 tr("sida {p} av {n}").format(p=f"{pages[0] + 1}" + (f"–{pages[-1] + 1}" if len(pages) > 1 else ""), n=n)]
        t = self.targets()
        if not self.guided():
            parts.append(tr("sidläge (G = ruta för ruta)"))
        elif not ready:
            parts.append(tr("söker rutor…"))
        elif ps:
            k = t[min(self.pidx, len(t) - 1)][2] if t else 0
            parts.append(tr("ruta {k}/{n}").format(k=k + 1, n=len(ps)) if k >= 0 else tr("helsida ({n} rutor)").format(n=len(ps)))
        elif len(t) > 1:
            parts.append(tr("del {k}/{n}").format(k=self.pidx + 1, n=len(t)))
        parts.append(tr("höger→vänster") if self.rtl else tr("vänster→höger"))
        d, tot = self.progress
        if tot and d < tot:
            parts.append(tr("detektering {d}/{n}").format(d=d, n=tot))
        if self.detector and not self.detector.ml_ok:
            parts.append(tr("ML av (bara CV)"))
        return parts

    def _hud(self, p):
        if not self.comic:
            self._text(p, self.msg or tr("Dra in en mapp, ett serie-arkiv, en PDF eller en bild hit") + "\n"
                       + tr("L = bläddra   Ctrl+O = öppna fil   Ctrl+L = senaste   F = helskärm   H = hjälp"),
                       center=True)
            return
        if self.hud_always or self.edit:  # full information bar only on request (I) and in edit mode
            self._text(p, "  ·  ".join(self.status_parts()))
        if self.msg:  # receipt: a small line at the top center, disappears by itself
            self._toast(p, self.msg)

    def _toast(self, p, s):
        k = self.ui_scale()
        p.setFont(QFont("Segoe UI", max(6, round(11 * k))))
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(s) + 28 * k
        h = fm.height() + 12 * k
        r = QRectF((self.width() - w) / 2, 14 * k, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(r, h / 2, h / 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor(235, 235, 235))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, s)

    def counter_text(self):
        """'p. 6/24 · panel 2/7' (or 'part 2/3' when the page is shown in several steps)."""
        pages = self.spreads[self.sp] if self.spreads else (self.page,)
        n = len(self.comic.pages)
        s = tr("s. {p}/{n}").format(p=f"{pages[0] + 1}" + (f"–{pages[-1] + 1}" if len(pages) > 1 else ""), n=n)
        t = self.targets()
        ps, ready = self.panels()
        if self.custom is None and not self.free and len(t) > 1:
            if self.guided() and ps:
                k = t[min(self.pidx, len(t) - 1)][2]
                s += "  ·  " + (tr("ruta {k}/{n}").format(k=k + 1, n=len(ps)) if k >= 0 else tr("helsida ({n} rutor)").format(n=len(ps)))
            else:
                s += "  ·  " + tr("del {k}/{n}").format(k=self.pidx + 1, n=len(t))
        elif self.guided() and not ready:
            s += "  ·  " + tr("söker rutor…")
        vis = self.anim_pages()
        if vis:
            a = self.anims[vis[0]]
            s += f"  ·  {'▶' if self.opt('anim_play') else '❚❚'} {a['k'] + 1}/{len(a['f'])}"
            if self._anim_speed() != 1.0:
                s += f" {self._anim_speed():g}x"
        d, tot = self.progress
        if tot and d < tot:
            s += "  ·  " + tr("rutor {d}/{n}").format(d=d, n=tot)
        return s

    def flash(self, msg=""):
        self.msg = msg
        self.hud_timer.start()
        self.update()

    def _clear_msg(self):
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

    def _scan_in_batches(self, comic):
        """More unscanned pages than detect_batch: scan all now or one batch at a time (asks if detect_large=ask)."""
        n = int(self.opt("detect_batch"))
        mode = self.opt("detect_large")
        if n <= 0 or mode == "all":
            return False
        left = sum(self.cache.get(p) is None for p in comic.pages)
        if left <= n:
            return False
        if mode == "batch":
            return True
        from PySide6.QtWidgets import QCheckBox, QMessageBox
        box = QMessageBox(QMessageBox.Icon.Question, "AutoComix",
                          tr("{title} har {left} sidor som inte är skannade efter rutor.").format(title=comic.title, left=left)
                          + "\n\n" + tr("Skanna alla nu, eller {n} i taget (nästa {n} skannas när du närmar dig slutet "
                                       "av de skannade)?").format(n=n), parent=self.window())
        every = box.addButton(tr("Skanna alla nu"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(tr("{n} i taget").format(n=n), QMessageBox.ButtonRole.RejectRole)
        keep = QCheckBox(tr("Kom ihåg valet (ändras under Inställningar)"))
        box.setCheckBox(keep)
        box.exec()
        batch = box.clickedButton() is not every
        if keep.isChecked():
            self.set_opt("detect_large", "batch" if batch else "all")
        return batch

    # ---------- slideshow / magnifier ----------
    def toggle_slideshow(self):
        if self.slideshow.isActive():
            self.slideshow.stop()
            self.flash(tr("Bildspel av"))
        elif self.comic:
            self.slideshow.start(int(self.opt("slideshow_ms")))
            how = tr("ruta för ruta") if self.opt("slideshow_mode") == "guided" and self.guided() else tr("sida för sida")
            self.flash(tr("Bildspel: {ms} ms per steg, {how}").format(ms=self.opt('slideshow_ms'), how=how))
        self.changed.emit()

    def _slide(self):
        """One slideshow step: next panel (guided mode) or next page; at the end possibly the next file or from the start."""
        if self.comic and self.opt("slideshow_wait_anim") and self.opt("anim_play"):
            if any(self.anims[p]["loops"] < 1 for p in self.anim_pages()):
                self.slideshow.setInterval(250)  # the animation has not played once yet: check again soon
                return
            self.slideshow.setInterval(int(self.opt("slideshow_ms")))
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
        if self.comic and self.opt("slideshow_loop"):
            self.first()  # the loop: start over from the first page/panel in the same file
            self.flash(tr("Bildspelet börjar om"))
            return
        self.slideshow.stop()
        self.flash(tr("Bildspelet är slut"))
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

    # ---------- edit panels ----------
    def toggle_edit(self):
        """Edit mode: the whole spread with numbered panels. Drag = new panel, right-click/Delete = delete,
        Ctrl+Z = undo. The corrections are saved per page and collected as training data for the model."""
        if not self.comic:
            return
        if self.opt("rotation"):
            self.flash(tr("Rotera tillbaka till 0° för att redigera rutor"))
            return
        self.edit = not self.edit
        self.edit_drag = None
        self.order_pick = None
        if self.edit:
            self.cursor_timer.stop()
            self.setCursor(Qt.CursorShape.CrossCursor)  # the mouse pointer is visible all the time in edit mode
            self.slideshow.stop()
            sp = self._spread(self.sp)
            self.custom = QRectF(0, 0, sp[0].width(), sp[0].height()) if sp else None
            self.free = False
            self._retarget(animate=False)
        else:
            self.custom = None
            self.unsetCursor()
            self._clamp_retarget()
            self.flash(tr("Rutorna sparade"))
        self.changed.emit()
        self.update()

    def _edit_boxes(self, p):
        ps, _ = self._page_panels(p)
        return [dict(q) for q in ps]

    def _edit_store(self, p, boxes):
        name = self.comic.pages[p]
        self._edit_push([p])
        self.user.set(name, boxes)
        self._training(p, boxes, "rättad")
        self.update()

    def _training(self, p, boxes, kind):
        """The page as JPEG + the panels as a training example (corrected or approved)."""
        try:
            import hashlib
            from PySide6.QtCore import QBuffer, QIODevice
            name = self.comic.pages[p]
            key = hashlib.sha1(f"{self.comic.path}|{name}".encode()).hexdigest()[:20]
            img = QImage.fromData(self.comic.read(p))
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "JPG", 92)
            save_training_example(bytes(buf.data()), boxes, key, kind)
        except Exception:
            pass

    def approve_page(self):
        """The page is correct: the current panels are saved as a training example (correct pages are needed in training too)."""
        if not self.comic or not self.spreads:
            return
        _ps, ready = self.panels()
        if not ready:
            self.flash(tr("Vänta tills rutorna är hittade"))
            return
        if self.opt("rotation"):
            self.flash(tr("Rotera tillbaka till 0° först"))
            return
        for p in self.spreads[self.sp]:
            self._training(p, self._edit_boxes(p), "godkänd")
        r, g = training_counts()
        self.flash(tr("Sidan godkänd  ·  träningsdata: {r} rättade, {g} godkända").format(r=r, g=g))

    # ---------- reading order ----------
    def toggle_order(self):
        """Order mode: click the panels in the order they should be read (starts edit mode if needed).
        The last panel is placed last automatically. Right-click undoes the last click, X/Esc cancels."""
        if not self.comic:
            return
        if self.order_pick is not None:
            self.order_pick = None
            self.flash(tr("Ordningen avbruten"))
            self.update()
            return
        if not self.edit:
            self.toggle_edit()
            if not self.edit:
                return
        self.order_pick = {"p": None, "seq": []}
        self.flash(tr("Klicka rutorna i läsordning"))
        self.update()

    def _order_hit(self, pt):
        """(page, panel index) for the smallest panel under the point (the spread's pixels), or (None, None)."""
        p, r = self._edit_page_at(pt)
        if p is None:
            return None, None
        boxes = self._edit_boxes(p)
        nx, ny = (pt.x() - r.x()) / r.width(), (pt.y() - r.y()) / r.height()
        hit = [k for k, b in enumerate(boxes) if b["x"] <= nx <= b["x"] + b["w"] and b["y"] <= ny <= b["y"] + b["h"]]
        return (p, min(hit, key=lambda k: G.area(boxes[k]))) if hit else (None, None)

    def order_click(self, pt):
        o = self.order_pick
        p, k = self._order_hit(pt)
        if p is None or (o["p"] is not None and p != o["p"]) or k in o["seq"]:
            return
        o["p"] = p
        o["seq"].append(k)
        boxes = self._edit_boxes(p)
        rest = [i for i in range(len(boxes)) if i not in o["seq"]]
        if len(rest) <= 1:  # sista rutan: klar
            seq = o["seq"] + rest
            self.order_pick = None
            self._edit_store(p, [dict(boxes[i], n=j) for j, i in enumerate(seq)])
            self.flash(tr("Läsordningen sparad"))
        self.update()

    def order_undo(self):
        o = self.order_pick
        if o["seq"]:
            o["seq"].pop()
        if not o["seq"]:
            o["p"] = None
        self.update()

    def order_auto(self):
        """Drop the custom reading order on the spread: the panels are kept, the order is computed automatically again."""
        if not self.comic or not self.spreads:
            return
        pages = [p for p in self.spreads[self.sp] if any("n" in b for b in (self.user.get(self.comic.pages[p]) or []))]
        if not pages:
            self.flash(tr("Ingen egen läsordning på sidan"))
            return
        self._edit_push(pages)
        for p in pages:
            self.user.set(self.comic.pages[p], [{k: v for k, v in b.items() if k != "n"}
                                                for b in self.user.get(self.comic.pages[p])])
        self._clamp_retarget(animate=False)
        self.flash(tr("Automatisk läsordning igen"))
        self.update()

    def _paint_order(self, p):
        o = self.order_pick
        sp = self._spread(self.sp)
        if not sp:
            return
        p.setFont(self.font(16, bold=True))
        for pg in self.spreads[self.sp]:
            r = sp[1][sp[2].index(pg)]
            for k, b in enumerate(self._edit_boxes(pg)):
                sr = self._to_screen(QRectF(r.x() + b["x"] * r.width(), r.y() + b["y"] * r.height(),
                                            b["w"] * r.width(), b["h"] * r.height()))
                done = o["p"] == pg and k in o["seq"]
                c = QColor(60, 200, 90) if done else QColor(150, 150, 150)
                p.setPen(QPen(c, 3))
                p.setBrush(QColor(c.red(), c.green(), c.blue(), 40))
                p.drawRect(sr)
                tag = QRectF(sr.x() + 4, sr.y() + 4, 34, 30)
                p.fillRect(tag, c)
                p.setPen(QColor(255, 255, 255))
                p.drawText(tag, Qt.AlignmentFlag.AlignCenter, str(o["seq"].index(k) + 1) if done else "?")
        p.setBrush(Qt.BrushStyle.NoBrush)
        self._text(p, tr("LÄSORDNING  ·  klicka rutorna i den ordning de ska läsas (den sista hamnar sist av sig själv)  ·  "
                         "högerklick = ångra senaste  ·  X/Esc = avbryt  ·  Shift+X = automatisk ordning igen"),
                   pos=(12, self.area_h() - 40))

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

    GRAB_PX = 9  # this close to the edge (screen pixels) counts as grabbing the edge

    def _edit_hit(self, pos, move=False):
        """(page, index, edges) for the panel whose edge/corner is under the mouse pointer; with move=True also the inside."""
        sp = self._spread(self.sp)
        if not sp:
            return None
        g = self.GRAB_PX
        best = None
        for r, pg in zip(sp[1], sp[2]):
            for k, b in enumerate(self._edit_boxes(pg)):
                sr = self._to_screen(QRectF(r.x() + b["x"] * r.width(), r.y() + b["y"] * r.height(),
                                            b["w"] * r.width(), b["h"] * r.height()))
                if not sr.adjusted(-g, -g, g, g).contains(pos):
                    continue
                edges = set()
                if abs(pos.x() - sr.left()) <= g:
                    edges.add("l")
                elif abs(pos.x() - sr.right()) <= g:
                    edges.add("r")
                if abs(pos.y() - sr.top()) <= g:
                    edges.add("t")
                elif abs(pos.y() - sr.bottom()) <= g:
                    edges.add("b")
                if move and not edges and sr.contains(pos):
                    edges = {"move"}
                if edges and (best is None or sr.width() * sr.height() < best[3]):
                    best = (pg, k, edges, sr.width() * sr.height())
        return best[:3] if best else None

    def _edit_cursor(self, pos, grab):
        """Pointer by what a drag does here: move/resize (grab) or draw a new panel (Shift)."""
        hit = self._edit_hit(pos, move=True) if grab else None
        if not hit:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return
        e = hit[2]
        if "move" in e:
            shape = Qt.CursorShape.SizeAllCursor
        elif e in ({"l", "t"}, {"r", "b"}):
            shape = Qt.CursorShape.SizeFDiagCursor
        elif e in ({"r", "t"}, {"l", "b"}):
            shape = Qt.CursorShape.SizeBDiagCursor
        elif e & {"l", "r"}:
            shape = Qt.CursorShape.SizeHorCursor
        else:
            shape = Qt.CursorShape.SizeVerCursor
        self.setCursor(shape)

    def _edit_grab_move(self, pt):
        """Updates the panel being dragged (the page's normalized coordinates) during resize/move."""
        pg, k, edges, orig, start = self.edit_grab
        sp = self._spread(self.sp)
        r = sp[1][sp[2].index(pg)]
        dx, dy = (pt.x() - start.x()) / r.width(), (pt.y() - start.y()) / r.height()
        x0, y0, x1, y1 = orig["x"], orig["y"], orig["x"] + orig["w"], orig["y"] + orig["h"]
        if "move" in edges:
            dx = min(max(dx, -x0), 1 - x1)
            dy = min(max(dy, -y0), 1 - y1)
            x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
        if "l" in edges:
            x0 = min(max(0.0, x0 + dx), x1 - 0.03)
        if "r" in edges:
            x1 = max(min(1.0, x1 + dx), x0 + 0.03)
        if "t" in edges:
            y0 = min(max(0.0, y0 + dy), y1 - 0.03)
        if "b" in edges:
            y1 = max(min(1.0, y1 + dy), y0 + 0.03)
        return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}

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
        boxes = [b for b in self._edit_boxes(p) if G.inter(b, q) / G.area(b) < 0.8]  # replaces panels it covers
        self._edit_store(p, boxes + [q])

    def _edit_push(self, pages):
        """Save the pages' panels before a change as an undo step; a new change empties the redo list."""
        self.edit_undo.append([(p, self.user.get(self.comic.pages[p])) for p in pages])
        self.edit_redo.clear()

    def _edit_swap(self, src, dst, label):
        if not (self.edit and src):
            return
        step = src.pop()
        dst.append([(p, self.user.get(self.comic.pages[p])) for p, _ in step])
        for p, boxes in step:
            self.user.set(self.comic.pages[p], boxes)
        self.flash(label)
        self.update()

    def edit_undo_last(self):
        self._edit_swap(self.edit_undo, self.edit_redo, tr("Ångrat"))

    def edit_redo_last(self):
        self._edit_swap(self.edit_redo, self.edit_undo, tr("Gjort om"))

    def edit_clear_page(self):
        """Delete all panels on the spread (to redraw from scratch). Ctrl+Z undoes."""
        if not self.edit:
            return
        pages = self.spreads[self.sp]
        self._edit_push(pages)
        for p in pages:
            self.user.set(self.comic.pages[p], [])
        self.flash(tr("Alla rutor borttagna – Ctrl+Z ångrar"))
        self.update()

    def edit_reset_page(self):
        """Back to automatic detection for the pages in the spread."""
        if not self.edit:
            return
        self._edit_push(self.spreads[self.sp])
        for p in self.spreads[self.sp]:
            self.user.set(self.comic.pages[p], None)
        self.update()

    def _paint_edit(self, p):
        if self.order_pick is not None:
            self._paint_order(p)
            return
        if self.edit_grab and self.edit_drag:
            pg, k, _e, _o, _s = self.edit_grab
            q = self._edit_grab_move(self.edit_drag[1])
            sp = self._spread(self.sp)
            r = sp[1][sp[2].index(pg)]
            p.setPen(QPen(QColor(90, 200, 255), 3))
            p.drawRect(self._to_screen(QRectF(r.x() + q["x"] * r.width(), r.y() + q["y"] * r.height(),
                                              q["w"] * r.width(), q["h"] * r.height())))
        ps, _ = self.panels()
        p.setFont(self.font(16, bold=True))
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
        if self.edit_drag and not self.edit_grab:
            a, b = self.edit_drag
            p.setPen(QPen(QColor(90, 200, 255), 2, Qt.PenStyle.DashLine))
            p.drawRect(self._to_screen(QRectF(a, b).normalized()))
        r, g = training_counts()
        self._text(p, tr("REDIGERA RUTOR  ·  dra utanför rutor = ny ruta  ·  dra i ruta = flytta  ·  dra i kant/hörn = ändra storlek  ·  "
                         "Shift+dra = ny ruta även över en ruta  ·  "
                         "högerklick/Delete = ta bort  ·  Ctrl+Delete = ta bort alla  ·  Ctrl+Z / Ctrl+Alt+Z = ångra / gör om  ·  "
                         "Ctrl+R = automatiskt igen  ·  K = sidan är rätt  ·  E = klar") + "\n"
                      + tr("Träningsdata: {r} rättade, {g} godkända sidor").format(r=r, g=g),
                   pos=(12, self.area_h() - 64))

    # ---------- inmatning ----------
    def next_dir(self, key_right):
        return (-1 if self.rtl else 1) * (1 if key_right else -1)

    def toggle_rtl(self):
        if not self.comic:
            return
        self.rtl = not self.rtl
        self.state.set_rtl(self.comic.path, self.rtl)
        self.sp_cache.clear()
        self.flash(tr("Läsriktning: {dir}").format(dir=tr("höger→vänster (japansk)") if self.rtl else tr("vänster→höger")))
        self.goto_page(self.page, animate=False)

    def _hide_cursor(self):
        if self.window().isFullScreen() and self.opt("hide_cursor") and not (self.mag_on or self.mag_hold or self.edit):
            self.setCursor(Qt.CursorShape.BlankCursor)

    def wheelEvent(self, e):
        if self.edit:
            return
        dy = e.angleDelta().y() or e.angleDelta().x()
        mods = e.modifiers()
        if self.mag_on or self.mag_hold:  # glass on: Shift+wheel = size, Ctrl+wheel = magnification
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self.mag_resize(1.1 if dy > 0 else 1 / 1.1)
                return
            if mods & Qt.KeyboardModifier.ControlModifier:
                self.mag_zoom_step(1.25 if dy > 0 else 0.8)
                return
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.15 if dy > 0 else 1 / 1.15, e.position())
            return
        self.wheel_acc += dy
        if abs(self.wheel_acc) >= 120:
            self.step(-1 if self.wheel_acc > 0 else 1)
            self.wheel_acc = 0

    def mousePressEvent(self, e):
        b = e.button()
        if self.edit and self.order_pick is not None:
            if b == Qt.MouseButton.LeftButton:
                self.order_click(self._to_page(e.position()))
            elif b == Qt.MouseButton.RightButton:
                self.order_undo()
            return
        if self.edit:
            if b == Qt.MouseButton.LeftButton:
                pt = self._to_page(e.position())
                shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                hit = None if shift else self._edit_hit(e.position(), move=True)  # Shift = always a new panel
                if hit:
                    pg, k, edges = hit
                    self.edit_grab = (pg, k, edges, self._edit_boxes(pg)[k], pt)
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
            else:
                self._edit_cursor(e.position(), not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            return
        self.unsetCursor()
        self.cursor_timer.start()
        if self.drag and e.buttons() & Qt.MouseButton.LeftButton:
            start, v, moved = self.drag
            d = e.position() - start
            if moved or abs(d.x()) + abs(d.y()) > 6:
                s = self._scale()
                if self.turn:
                    d = QTransform().rotate(-self.turn).map(d)
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
                if self.edit_grab:  # resize/move of an existing panel
                    q = self._edit_grab_move(c)
                    pg, k = self.edit_grab[0], self.edit_grab[1]
                    self.edit_grab = None
                    boxes = self._edit_boxes(pg)
                    boxes[k] = q
                    self._edit_store(pg, boxes)
                else:
                    self.edit_add(a, c)
                self._edit_cursor(e.position(), True)  # ready for the next panel right away
            return
        if b == Qt.MouseButton.LeftButton and self.drag and not self.drag[2]:
            pos = e.position()
            if self.comic and self.opt("show_progress") and pos.y() > self.height() - 14:
                frac = pos.x() / self.width()
                self.goto_page(int((1 - frac if self.rtl else frac) * len(self.comic.pages)))
            else:
                x = pos.x() / self.width()
                if x > 0.8:  # narrow edge zones so double-clicks on panels in the middle work
                    self.step(self.next_dir(True))
                elif x < 0.2:
                    self.step(self.next_dir(False))
                else:
                    self.update()
        elif b == Qt.MouseButton.RightButton:
            self.contextMenu.emit(e.globalPosition())
        elif b == Qt.MouseButton.MiddleButton:
            self.mag_hold = False
            self.update()
        self.drag = None

    def mouseDoubleClickEvent(self, e):
        """Like Smart Comic Reader: double-clicking a panel zooms to it. Double-clicking a zoomed panel = whole page."""
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
            self.custom = full  # back to the whole spread
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
            if q is None:  # no panel found: zoom to half the page around the point
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
        """Several files from the same folder: open the folder from the start (in the chosen sorting) instead of at the first file."""
        ps = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.toLocalFile()]
        if len(ps) > 1 and all(p.is_file() and p.suffix.lower() in IMAGE_EXT for p in ps) \
                and len({p.parent for p in ps}) == 1:
            self.open(ps[0].parent)
        elif ps:
            self.open(ps[0])
