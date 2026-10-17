"""Andra skärmen: spegling eller automatisk fördelning (liggande/stående) av huvudfönstrets visning.

Fönstret tar aldrig fokus – tangenter och handkontroll styr huvudfönstret, och den här skärmen följer efter.
Spegling: samma ruta/sida, anpassad till den här skärmens proportioner.
Fördelning: liggande rutor/sidor visas på den liggande skärmen och stående på den stående; den andra skärmen
behåller sin senaste bild.
"""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

MODES = (("off", "Av"), ("mirror", "Spegling"), ("auto", "Automatisk fördelning (liggande/stående)"))
# Anpassning av hela sidor på andra skärmen (rutor visas alltid hela och så stora som möjligt)
FITS = (("screen", "Andra skärmen: anpassa till skärm"), ("width", "Andra skärmen: anpassa till bredd"),
        ("height", "Andra skärmen: anpassa till höjd"), ("main", "Andra skärmen: samma utsnitt som huvudfönstret"))


def wide(r):
    return r.width() > r.height() * 1.05


def fit_aspect(r, ar, full, clamp):
    """r utvidgad till proportionerna ar (bredd/höjd), centrerad; clamp håller den inom bilden (som Viewer._fit_aspect)."""
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
    """frame = (bild, visningsfönster, fokus, bakgrund). Ritar som Viewer: fönstret anpassat, bakgrundsfärg runt fokus."""
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
        self.setWindowTitle("PanelView – andra skärmen")
        self.v = viewer
        self.mode = "off"
        self.live = True        # visar aktuell ruta (annars self.held)
        self.held = None        # senaste bilden som hörde till den här skärmen
        self.main_last = None   # senaste bilden huvudskärmen visade – fryses där när aktuell bild flyttas hit
        viewer.painted.connect(self._follow)
        QGuiApplication.instance().screenAdded.connect(lambda _s: self.relocate())
        QGuiApplication.instance().screenRemoved.connect(lambda _s: self.relocate())

    # ---------- skärmval ----------
    def _main_screen(self):
        return self.v.window().screen()

    def target_screen(self):
        """En annan skärm än huvudfönstrets; helst en med motsatt orientering."""
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

    def same_orientation(self):
        return self.here_wide() == self.main_wide()

    def set_mode(self, mode):
        """Byter läge. Returnerar ett meddelande att visa, eller tom sträng."""
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
            return "Hittar ingen andra skärm"
        self._follow()
        if mode == "auto" and self.same_orientation():
            return "Skärmarna har samma orientering – fördelningen fungerar som spegling"
        return ""

    def relocate(self):
        """Lägg fönstret i helskärm på den andra skärmen (även efter att skärmar kopplats in/ur eller huvudfönstret flyttats)."""
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

    # ---------- följa huvudfönstret ----------
    def _follow(self):
        """Anropas efter varje ritning i huvudfönstret."""
        if self.mode == "off" or not self.isVisible():
            return
        v = self.v
        fin = v.frame(final=True)
        if self.mode == "mirror" or fin is None or self.same_orientation():
            self.live = True
            if v.frozen is not None:
                v.frozen = None
                v.update()
        elif wide(fin[2]) == self.here_wide():  # aktuell bild hör hit
            if v.frozen is None:
                v.frozen = self.main_last or (None, QRectF(), QRectF(), fin[3])
                v.update()
            self.live, self.held = True, fin
        else:  # aktuell bild hör till huvudskärmen
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
        if focus != full:  # ruta: hela rutan, så stor som möjligt
            own = fit_aspect(focus, ar, full, clamp=not dim)
        else:
            own = self.page_view(full, view, ar)
        q = v.opt("quality")
        paint_frame(p, self.width(), self.height(), (img, own, focus, bg), dim,
                    q == "best" or (q == "smooth" and not v.animating))

    def page_view(self, full, main_view, ar):
        """Utsnitt för en hel sida enligt andra skärmens egen anpassning. Bläddrar huvudfönstret i sidan
        (bredd/höjd/zoom) följer utsnittet med i samma riktning."""
        fit = self.v.state.setting("second_fit", "screen")
        if fit == "main":
            return fit_aspect(main_view, ar, full, clamp=True)
        if fit == "width":
            w, h = full.width(), full.width() / ar
        elif fit == "height":
            w, h = full.height() * ar, full.height()
        else:
            return fit_aspect(full, ar, full, clamp=False)
        c = main_view.center()
        x = (full.width() - w) / 2 if w >= full.width() else min(max(c.x() - w / 2, 0), full.width() - w)
        y = (full.height() - h) / 2 if h >= full.height() else min(max(c.y() - h / 2, 0), full.height() - h)
        return QRectF(x, y, w, h)
