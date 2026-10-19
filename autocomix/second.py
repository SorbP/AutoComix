"""Second screen: mirroring or automatic distribution (landscape/portrait) of the main window's view.

The window never takes focus – keys (and the phone remote) control the main window, and this screen follows.
Mirroring: the same panel/page, fitted to this screen's proportions.
Distribution: landscape panels/pages are shown on the landscape screen and portrait ones on the portrait screen; the
other screen keeps its last image.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from .i18n import tr

MODES = (("off", tr("Av")), ("mirror", tr("Spegling")), ("auto", tr("Automatisk fördelning (liggande/stående)")))
# Fit of whole pages on the second screen (panels are always shown whole and as large as possible)
FITS = (("screen", tr("Andra skärmen: anpassa till skärm")), ("width", tr("Andra skärmen: anpassa till bredd")),
        ("height", tr("Andra skärmen: anpassa till höjd")), ("main", tr("Andra skärmen: samma utsnitt som huvudfönstret")))
SIDES = (("left", tr("Vänster skärm")), ("right", tr("Höger skärm")))


def side_of(widget):
    """'left'/'right' by the physical screen the widget is shown on (smallest x = left). One screen: left."""
    scrs = QGuiApplication.screens()
    if len(scrs) < 2:
        return "left"
    return "left" if widget.screen() is min(scrs, key=lambda s: s.geometry().x()) else "right"


def fit_key(side, mode):
    """Settings key for the fit: separate values per side, and separate ones when mirroring."""
    return f"fit_{side}" + ("_mirror" if mode == "mirror" else "")


def migrate_fits(state):
    """First time: left = the main window's old 'fit', right = the second screen's old 'second_fit'."""
    for side, old in (("left", "fit"), ("right", "second_fit")):
        for mode in ("off", "mirror"):
            if state.setting(fit_key(side, mode)) is None:
                state.set_setting(fit_key(side, mode), state.setting(old, "screen"))


def wide(r):
    return r.width() > r.height() * 1.05


def fit_aspect(r, ar, full, clamp):
    """r expanded to the proportions ar (width/height), centered; clamp keeps it inside the image (like Viewer._fit_aspect)."""
    w, h = r.width(), r.height()
    if w / max(h, 1e-6) < ar:
        w = h * ar
    else:
        h = w / ar
    x, y = r.center().x() - w / 2, r.center().y() - h / 2
    if clamp:
        x = (full.width() - w) / 2 if w >= full.width() else min(max(x, 0), full.width() - w)
        y = (full.height() - h) / 2 if h >= full.height() else min(max(y, 0), full.height() - h)
    return QRectF(x, y, w, h)


def paint_frame(p, W, H, frame, dim, smooth):
    """frame = (image, view window, focus, background). Draws like Viewer: the window fitted, background color around the focus."""
    img, view, focus, bg = frame
    p.fillRect(QRectF(0, 0, W, H), bg)
    if img is None or view.isEmpty():
        return
    s = min(W / max(view.width(), 1e-6), H / max(view.height(), 1e-6))
    ox, oy = (W - view.width() * s) / 2 - view.x() * s, (H - view.height() * s) / 2 - view.y() * s

    def to(r):
        return QRectF(ox + r.x() * s, oy + r.y() * s, r.width() * s, r.height() * s)
    full = QRectF(0, 0, img.width(), img.height())
    src = view.intersected(full)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
    p.drawImage(to(src), img, src)
    if dim and focus != full:
        f = to(focus)
        p.fillRect(QRectF(0, 0, W, f.top()), bg)
        p.fillRect(QRectF(0, f.bottom(), W, H - f.bottom()), bg)
        p.fillRect(QRectF(0, f.top(), f.left(), f.height()), bg)
        p.fillRect(QRectF(f.right(), f.top(), W - f.right(), f.height()), bg)


class SecondScreen(QWidget):
    def __init__(self, viewer):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setWindowTitle(tr("AutoComix – andra skärmen"))
        self.v = viewer
        self.mode = "off"
        self.live = True        # shows the current panel (otherwise self.held)
        self.held = None        # the last image that belonged to this screen
        self.main_last = None   # the last image the main screen showed – frozen there when the current image moves here
        viewer.fit_key = lambda: fit_key(side_of(viewer.window()), self.mode)
        viewer.painted.connect(self._follow)
        QGuiApplication.instance().screenAdded.connect(lambda _s: self.relocate())
        QGuiApplication.instance().screenRemoved.connect(lambda _s: self.relocate())

    # ---------- screen choice ----------
    def _main_screen(self):
        return self.v.window().screen()

    def target_screen(self):
        """A screen other than the main window's; preferably one with the opposite orientation."""
        main = self._main_screen()
        others = [s for s in QGuiApplication.screens() if s is not main]
        if not others:
            return None
        mw = wide(QRectF(main.geometry()))
        return next((s for s in others if wide(QRectF(s.geometry())) != mw), others[0])

    def here_wide(self):
        return wide(QRectF(self.screen().geometry()))

    def main_wide(self):
        return wide(QRectF(self._main_screen().geometry()))

    def side(self):
        """This screen's side; without a screen of its own (hidden, or on the main window's screen) opposite the main window."""
        if self.isVisible() and self.screen() is not self._main_screen():
            return side_of(self)
        return "right" if side_of(self.v.window()) == "left" else "left"

    def fit(self):
        return self.v.state.setting(fit_key(self.side(), self.mode), "screen")

    def same_orientation(self):
        return self.here_wide() == self.main_wide()

    def set_mode(self, mode):
        """Changes mode. Returns a message to show, or an empty string."""
        self.mode = mode
        self.held = self.main_last = None
        self.live = True
        self.v.frozen = None
        self.v.update()
        if mode == "off":
            self.hide()
            return ""
        if not self.relocate():
            self.mode = "off"
            return tr("Hittar ingen andra skärm")
        self._follow()
        if mode == "auto" and self.same_orientation():
            return tr("Skärmarna har samma orientering – fördelningen fungerar som spegling")
        return ""

    def relocate(self):
        """Put the window in full screen on the second screen (also after screens were plugged in/out or the main window moved)."""
        if self.mode == "off":
            return False
        scr = self.target_screen()
        if scr is None:
            self.hide()
            self.v.frozen = None
            self.v.update()
            return False
        self.hide()
        self.setGeometry(scr.geometry())
        self.show()
        if self.windowHandle():
            self.windowHandle().setScreen(scr)
        self.setGeometry(scr.geometry())
        self.showFullScreen()
        return True

    # ---------- following the main window ----------
    def _follow(self):
        """Called after every paint in the main window."""
        if self.mode == "off" or not self.isVisible():
            return
        v = self.v
        fin = v.frame(final=True)
        if self.mode == "mirror" or fin is None or self.same_orientation():
            self.live = True
            if v.frozen is not None:
                v.frozen = None
                v.update()
        elif wide(fin[2]) == self.here_wide():  # the current image belongs here
            if v.frozen is None:
                v.frozen = self.main_last or (None, QRectF(), QRectF(), fin[3])
                v.update()
            self.live, self.held = True, fin
        else:  # the current image belongs to the main screen
            if v.frozen is not None:
                v.frozen = None
                v.update()
            self.live, self.main_last = False, fin
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        v = self.v
        fr = v.frame(final=self.mode == "auto") if self.live else self.held
        if fr is None:
            p.fillRect(self.rect(), v.bg_color() if v.comic else QColor(12, 12, 12))
            return
        img, view, focus, bg = fr
        if img is None:
            p.fillRect(self.rect(), bg)
            return
        full = QRectF(0, 0, img.width(), img.height())
        dim = v.opt("dim") and not (self.live and v.free)
        ar = self.width() / max(self.height(), 1)
        if focus != full:  # panel: the whole panel, as large as possible
            own = fit_aspect(focus, ar, full, clamp=not dim)
        else:
            own = self.page_view(full, view, ar)
        q = v.opt("quality")
        paint_frame(p, self.width(), self.height(), (img, own, focus, bg), dim,
                    q == "best" or (q == "smooth" and not v.animating))

    def page_view(self, full, main_view, ar):
        """View for a whole page by the second screen's own fit. If the main window scrolls in the page
        (width/height/zoom), the view follows in the same direction."""
        fit = self.fit()
        if fit == "main":
            return fit_aspect(main_view, ar, full, clamp=True)
        if fit == "width":
            w, h = full.width(), full.width() / ar
        elif fit == "height":
            w, h = full.height() * ar, full.height()
        elif fit == "original":  # 100 % (or the chosen zoom) in this screen's pixels
            z = float(self.v.opt("zoom"))
            w, h = self.width() / z, self.height() / z
        else:
            return fit_aspect(full, ar, full, clamp=False)
        c = main_view.center()
        x = (full.width() - w) / 2 if w >= full.width() else min(max(c.x() - w / 2, 0), full.width() - w)
        y = (full.height() - h) / 2 if h >= full.height() else min(max(c.y() - h / 2, 0), full.height() - h)
        return QRectF(x, y, w, h)
