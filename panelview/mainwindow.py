"""Huvudfönster: menyer, kortkommandon (ändringsbara), dialoger för inställningar, bokmärken, miniatyrer och utskrift.

Funktionsuppsättningen följer CDisplayEx (se FEATURES.md) plus PanelViews guidade rutzoom.
"""
import sys
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QRectF, QRunnable, QSize, Qt, QThreadPool, QTimer, QObject, Signal
from PySide6.QtGui import (QAction, QActionGroup, QColor, QGuiApplication, QIcon, QImage, QKeySequence,
                           QFont, QPainter, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
                               QInputDialog, QKeySequenceEdit, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMenuBar, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import __version__
from .comic import ARCHIVE_EXT, IMAGE_EXT
from .store import State
from .overlays import Progress
from .second import FITS as SECOND_FITS, MODES as SECOND_MODES, SIDES, SecondScreen, fit_key, migrate_fits, side_of
from .viewer import DEFAULTS, MAG_SHAPES, Viewer

FILTER = "Serier och bilder ({});;Alla filer (*)".format(
    " ".join(f"*{e}" for e in sorted(ARCHIVE_EXT | set(IMAGE_EXT))))

FITS = [("screen", "Anpassa till skärm"), ("width", "Anpassa till bredd"), ("height", "Anpassa till höjd"),
        ("original", "Originalstorlek (100 %)")]
ZOOMS = [1.25, 1.5, 2.0, 4.0]
SLIDE_STEPS = (500, 1000, 1500, 2000, 3000, 5000, 8000, 10000, 15000, 30000)  # bildspelets tider (ms), Alt+Upp/Ned


class MainWindow(QMainWindow):
    def __init__(self, path=None):
        super().__init__()
        self.state = State()
        self.v = Viewer(self.state)
        self.setCentralWidget(self.v)
        self.second = SecondScreen(self.v)
        migrate_fits(self.state)
        self.setAcceptDrops(True)
        self.resize(1280, 900)
        self.acts = {}
        self._build_actions()
        self._build_menus()
        self.v.changed.connect(self._sync)
        self.v.contextMenu.connect(self._context)
        self.v.passwordNeeded.connect(self._ask_password)
        self.v.finished.connect(self._finished)
        self._restore_geometry()
        self._sync()
        self._left_full = 0.0
        self.persist = QTimer(self, singleShot=True, interval=1500, timeout=self._persist)
        self.v.changed.connect(self.persist.start)
        self._build_top_bar()
        self.apply_ui_scale()
        if path:
            self.v.open(path)

    def _persist(self):
        """Spara sida/ruta löpande (inte bara vid stängning) så att Ctrl+L/historiken hittar rätt även efter en krasch."""
        v = self.v
        if v.comic:
            self.state.set_page(v.comic.path, v.page, v.pidx)
        self.state.save()

    # ---------- menyrad i helskärm ----------
    def _build_top_bar(self):
        """Helskärm: menyraden visas när musen förs till överkanten. Den ligger ovanpå bilden (flyttar den inte) och
        delar menyer med den vanliga menyraden."""
        self.top_bar = QMenuBar(self)
        for m in self.menus:
            self.top_bar.addMenu(m)
            m.aboutToHide.connect(lambda: self.top_hide.start())
        self.top_bar.hide()
        self.top_hide = QTimer(self, singleShot=True, interval=500, timeout=self._maybe_hide_top)
        self.v.installEventFilter(self)

    def eventFilter(self, obj, e):
        if obj is self.v and e.type() == QEvent.Type.MouseMove and self.isFullScreen():
            y = self._mouse_y = e.position().y()
            if y <= 2 and not e.buttons():
                self._show_top()
            elif self.top_bar.isVisible() and y > self.top_bar.height() + 40:
                self.top_hide.start()
        return False

    def _show_top(self):
        self.top_hide.stop()
        if not self.top_bar.isVisible():
            self.top_bar.setGeometry(0, 0, self.width(), self.top_bar.sizeHint().height())
            self.top_bar.raise_()
            self.top_bar.show()

    def _maybe_hide_top(self):
        near = getattr(self, "_mouse_y", 0) <= self.top_bar.height() + 40  # senaste läget över bilden
        if QApplication.activePopupWidget() or (near and self.isFullScreen()):
            self.top_hide.start()  # meny öppen eller musen kvar vid kanten: vänta
        else:
            self.top_bar.hide()

    # ---------- åtgärder ----------
    def _act(self, key, label, keys=(), fn=None, check=None, menu=None):
        a = QAction(label, self)
        a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        a.setProperty("default_keys", list(keys))
        if check is not None:
            a.setCheckable(True)
            a.setProperty("check", check)
        if fn:
            a.triggered.connect(lambda _=False, f=fn: f())
        self.acts[key] = a
        self.addAction(a)  # kortkommandon fungerar även med dold menyrad (helskärm)
        return a

    def _build_actions(self):
        v, A = self.v, self._act
        # Arkiv
        A("open_file", "Öppna fil…", ["Ctrl+O", "O"], self.open_file)
        A("open_folder", "Öppna mapp…", ["Ctrl+Shift+O", "Shift+O"], self.open_folder)
        A("browse", "Bläddra bland serier (med förhandsvisning)…", ["L"], self.browse)
        A("resume", "Återuppta senaste", ["Ctrl+L"], self.resume_last)
        A("next_file", "Nästa fil", ["N", "Ctrl+Right"], lambda: v.sibling(1))
        A("prev_file", "Föregående fil", ["B", "Shift+N", "Ctrl+Left"], lambda: v.sibling(-1))
        A("save_page", "Spara sida som…", ["Ctrl+S"], self.save_page)
        A("copy_page", "Kopiera sida", ["Ctrl+C"], self.copy_page)
        A("print", "Skriv ut…", ["Ctrl+P"], self.print_page)
        A("close_file", "Stäng fil", ["Ctrl+W"], v.close_comic)
        A("history", "Visningshistorik…", ["Ctrl+Shift+H"], self.show_history)
        A("clear_history", "Rensa historik", [], self.clear_history)
        A("exit", "Avsluta", ["Ctrl+Q"], self.close)
        # Navigera
        A("next", "Nästa (ruta/del/sida)", ["Space", "Down"], lambda: self.nav(1))
        A("prev", "Föregående", ["Backspace", "Up"], lambda: self.nav(-1))
        A("right", "Höger (följer läsriktningen)", ["Right"], lambda: self.nav(v.next_dir(True), arrow=True))
        A("left", "Vänster (följer läsriktningen)", ["Left"], lambda: self.nav(v.next_dir(False), arrow=True))
        A("enter", "Helskärm (Enter)", ["Return", "Enter"], self.enter)
        A("next_page", "Nästa sida", ["PgDown"], lambda: v.page_step(1))
        A("prev_page", "Föregående sida", ["PgUp"], lambda: v.page_step(-1))
        A("first", "Första sidan", ["Home"], v.first)
        A("last", "Sista sidan", ["End"], v.last)
        A("goto", "Gå till sida…", ["J", "Ctrl+G"], self.goto_dialog)
        A("thumbbar", "Miniatyrlist", ["Ctrl+T"], v.toggle_thumbbar, check=lambda: v.thumbbar.isVisible())
        A("slider", "Sidreglage", ["Ctrl+I"], v.toggle_slider, check=lambda: v.slider.isVisible())
        A("thumbs", "Miniatyröversikt…", ["T"], self.thumbnails)
        A("slideshow", "Automatiskt bildspel (ruta för ruta i guidat läge)", ["Ctrl+H", "S"], v.toggle_slideshow,
          check=lambda: v.slideshow.isActive())
        A("slide_longer", "Bildspel: längre tid per steg", ["Alt+Up"], lambda: self.slide_ms_step(1))
        A("slide_shorter", "Bildspel: kortare tid per steg", ["Alt+Down"], lambda: self.slide_ms_step(-1))
        # Animation (GIF/WebP/APNG)
        A("anim_play", "Spela animationer", ["P", "Ctrl+Space"], v.toggle_anim, check=lambda: v.opt("anim_play"))
        A("anim_next", "Nästa bildruta", ["."], lambda: v.anim_step(1))
        A("anim_prev", "Föregående bildruta", [","], lambda: v.anim_step(-1))
        A("anim_faster", "Snabbare", ["Ctrl+Up"], lambda: v.anim_speed_step(1))
        A("anim_slower", "Långsammare", ["Ctrl+Down"], lambda: v.anim_speed_step(-1))
        A("anim_normal", "Normal hastighet", ["Ctrl+Shift+0"], lambda: v.set_anim_speed(1.0))
        A("slideshow_wait_anim", "Bildspelet väntar tills animationen gått ett varv", [],
          lambda: self._toggle("slideshow_wait_anim"), check=lambda: v.opt("slideshow_wait_anim"))
        # Visa
        A("fullscreen", "Helskärm", ["F", "F11"], self.toggle_fullscreen, check=self.isFullScreen)
        A("menubar", "Visa menyrad", ["Ctrl+M"], self.toggle_menubar, check=lambda: self.state.setting("menubar", True))
        A("guided", "Guidat läge (ruta för ruta)", ["G"], lambda: self._toggle("guided"), check=lambda: v.opt("guided"))
        A("overview", "Visa hela sidan före rutorna", ["V"], lambda: self._toggle("overview"), check=lambda: v.opt("overview"))
        A("dim", "Svart runt rutan", ["D"], lambda: self._toggle("dim"), check=lambda: v.opt("dim"))
        A("rtl", "Japanskt läge (höger→vänster)", ["R"], v.toggle_rtl, check=lambda: v.rtl)
        A("double", "Dubbelsida", ["Shift+D"], lambda: self._toggle("double"), check=lambda: v.opt("double"))
        A("cover_single", "Omslaget ensamt", [], lambda: self._toggle("cover_single"), check=lambda: v.opt("cover_single"))
        A("shadow", "Skugga i bokryggen", [], lambda: self._toggle("shadow"), check=lambda: v.opt("shadow"))
        # 1-4 = vänster skärm, Num+1-4 (numpadden) = höger skärm; "fit_*" behåller namnet (egna tangenter finns kvar)
        for side, pre, keys in (("left", "fit_", "{}"), ("right", "fit_right_", "Num+{}")):
            for i, (k, label) in enumerate(FITS):
                A(pre + k, f"{dict(SIDES)[side]}: {label[0].lower()}{label[1:]}", [keys.format(i + 1)],
                  lambda k=k, side=side: self.set_fit(k, side=side),
                  check=lambda k=k, side=side: self.fit_of(side) == k and (k != "original" or v.opt("zoom") == 1.0))
        for z in ZOOMS:
            A(f"zoom_{int(z * 100)}", f"Zoom {int(z * 100)} %", [], lambda z=z: self.set_fit("original", z),
              check=lambda z=z: self.fit_of(side_of(self)) == "original" and v.opt("zoom") == z)
        for k, label in (("shrink_w", "Krymp bilder bredare än skärmen"), ("grow_w", "Förstora bilder smalare än skärmen"),
                         ("shrink_h", "Krymp bilder högre än skärmen"), ("grow_h", "Förstora bilder lägre än skärmen")):
            A(k, label, [], lambda k=k: self._toggle(k), check=lambda k=k: v.opt(k))
        A("zoom_in", "Zooma in", ["+", "=", "Ctrl++"], lambda: v.zoom(1.25))
        A("zoom_out", "Zooma ut", ["-", "Ctrl+-"], lambda: v.zoom(0.8))
        A("zoom_reset", "Återställ zoom", ["0"], v.reset_zoom)
        A("rot_left", "Rotera vänster", ["["], lambda: self.rotate(-90))
        A("rot_right", "Rotera höger", ["]"], lambda: self.rotate(90))
        A("magnifier", "Förstoringsglas (eller håll mittenknappen)", ["M"], v.toggle_magnifier, check=lambda: v.mag_on)
        for k, label in MAG_SHAPES:
            A("mag_" + k, label, [], lambda k=k: v.set_mag_shape(k), check=lambda k=k: v.opt("mag_shape") == k)
        A("mag_bigger", "Större glas (eller Shift+hjul)", [], lambda: v.mag_resize(1.15))
        A("mag_smaller", "Mindre glas", [], lambda: v.mag_resize(1 / 1.15))
        A("mag_more", "Mer förstoring (eller Ctrl+hjul)", [], lambda: v.mag_zoom_step(1.25))
        A("mag_less", "Mindre förstoring", [], lambda: v.mag_zoom_step(0.8))
        A("info", "Informationsrad alltid", ["I"], self.toggle_info, check=lambda: v.hud_always)
        A("pagenum", "Sidnummer", [], lambda: self._toggle("show_pagenum"), check=lambda: v.opt("show_pagenum"))
        A("progress", "Förloppslist (klickbar)", [], lambda: self._toggle("show_progress"), check=lambda: v.opt("show_progress"))
        A("distance", "Avståndsläge (stor sidräknare, döljs vid inaktivitet)", ["Shift+F"],
          lambda: (v.toggle_distance(), self.apply_ui_scale()),
          check=lambda: v.opt("distance_mode"))
        for k, label in SECOND_MODES:
            A("second_" + k, label, [], lambda k=k: self.set_second(k), check=lambda k=k: self.second.mode == k)
        A("second_cycle", "Andra skärmen: växla läge (av/spegling/fördelning)", ["F9"], self.cycle_second)
        for k, label in SECOND_FITS:
            A("second_fit_" + k, label, [], lambda k=k: self.set_second_fit(k),
              check=lambda k=k: self.second.fit() == k)
        A("second_fit_cycle", "Andra skärmen: växla anpassning (skärm/bredd/höjd/som huvudfönstret)", ["Shift+F9"],
          self.cycle_second_fit)
        A("ui_bigger", "Större gränssnitt", ["Ctrl+Shift+Up"], lambda: self.ui_scale_step(1))
        A("ui_smaller", "Mindre gränssnitt", ["Ctrl+Shift+Down"], lambda: self.ui_scale_step(-1))
        # Bild
        A("auto_color", "Automatisk färgkorrigering", ["A"], lambda: self._toggle("auto_color"), check=lambda: v.opt("auto_color"))
        A("bg_color", "Bakgrundsfärg…", [], self.pick_bg)
        A("bg_auto", "Automatisk bakgrundsfärg", [], self.toggle_bg_auto, check=lambda: v.opt("bg") == "auto")
        # Bokmärken
        A("edit", "Redigera rutor (rita/ta bort, sparas)", ["E"], v.toggle_edit, check=lambda: v.edit)
        A("approve", "Sidan är rätt (spara som träningsdata)", ["K", "Ctrl+Return"], v.approve_page)
        A("edit_del", "Ta bort rutan under musen", ["Delete"], v.edit_delete_under_mouse)
        A("edit_clear", "Ta bort alla rutor (uppslaget)", ["Ctrl+Delete"], v.edit_clear_page)
        A("edit_undo", "Ångra rutändring", ["Ctrl+Z"], v.edit_undo_last)
        A("edit_redo", "Gör om rutändring", ["Ctrl+Alt+Z"], v.edit_redo_last)
        A("edit_reset", "Automatiska rutor igen (uppslaget)", ["Ctrl+R"], v.edit_reset_page)
        A("order_pick", "Ändra läsordning (klicka rutorna i ordning)", ["X"], v.toggle_order,
          check=lambda: v.order_pick is not None)
        A("order_auto", "Automatisk läsordning igen (uppslaget)", ["Shift+X"], v.order_auto)
        A("order_xy", "Läsordning: kolumn bredvid hög ruta först (4-6-5 i stället för 4-5-6)", [],
          lambda: self._toggle("order_xy"), check=lambda: v.opt("order_xy"))
        A("bm_add", "Lägg till bokmärke…", ["Ctrl+B"], self.add_bookmark)
        A("bm_manage", "Hantera bokmärken…", ["Ctrl+Shift+B"], self.manage_bookmarks)
        # Inställningar / hjälp
        A("options", "Inställningar…", ["Ctrl+,", "F12"], self.options)
        A("help", "Kortkommandon", ["H", "F1", "?"], self.toggle_help, check=lambda: v.show_help)
        A("about", "Om PanelView", [], self.about)
        A("escape", "Lämna helskärm / stäng hjälp / avsluta", ["Esc"], self.escape)
        self._apply_keys()

    def _apply_keys(self):
        custom = self.state.keys()
        for k, a in self.acts.items():
            seqs = custom.get(k, a.property("default_keys"))
            a.setShortcuts([QKeySequence(s) for s in seqs if s])

    def _build_menus(self):
        mb = self.menuBar()
        a = self.acts
        m = mb.addMenu("&Arkiv")
        for k in ("browse", "open_file", "open_folder"):
            m.addAction(a[k])
        self.recent_menu = m.addMenu("Öppna senaste")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        for k in ("resume", "history", None, "next_file", "prev_file", None, "save_page", "copy_page", "print", None,
                  "close_file", "clear_history", None, "exit"):
            m.addSeparator() if k is None else m.addAction(a[k])
        m = mb.addMenu("&Navigera")
        for k in ("next", "prev", "right", "left", None, "next_page", "prev_page", "first", "last", "goto", None,
                  "thumbbar", "slider", "thumbs"):
            m.addSeparator() if k is None else m.addAction(a[k])
        sm = m.addMenu("Bildspel")
        sm.aboutToShow.connect(lambda sm=sm: (sm.clear(), self.slideshow_menu(sm)))
        am = m.addMenu("Animation (GIF/WebP/APNG)")
        for k in ("anim_play", None, "anim_next", "anim_prev", None, "anim_faster", "anim_slower", "anim_normal",
                  None, "slideshow_wait_anim"):
            am.addSeparator() if k is None else am.addAction(a[k])
        m = mb.addMenu("&Visa")
        for k in ("fullscreen", "menubar", None, "guided", "overview", "dim", None, "rtl", "double", "cover_single",
                  "shadow"):
            m.addSeparator() if k is None else m.addAction(a[k])
        fm = m.addMenu("Anpassning")
        g = QActionGroup(self)
        for pre in ("fit_", "fit_right_"):
            g = QActionGroup(self)
            for k, _ in FITS:
                fm.addAction(a[pre + k])
                g.addAction(a[pre + k])
            fm.addSeparator()
        g = QActionGroup(self)
        for z in ZOOMS:
            fm.addAction(a[f"zoom_{int(z * 100)}"])
            g.addAction(a[f"zoom_{int(z * 100)}"])
        fm.addSeparator()
        for k in ("shrink_w", "grow_w", "shrink_h", "grow_h"):
            fm.addAction(a[k])
        for k in (None, "zoom_in", "zoom_out", "zoom_reset", None, "rot_left", "rot_right", None):
            m.addSeparator() if k is None else m.addAction(a[k])
        gm = m.addMenu("Förstoringsglas")
        for k in ("magnifier", None, *("mag_" + x for x, _ in MAG_SHAPES), None,
                  "mag_bigger", "mag_smaller", "mag_more", "mag_less"):
            gm.addSeparator() if k is None else gm.addAction(a[k])
        for k in ("info", "pagenum", "progress", None, "distance", "ui_bigger", "ui_smaller", None):
            m.addSeparator() if k is None else m.addAction(a[k])
        dm = m.addMenu("Andra skärmen")
        g = QActionGroup(self)
        for k, _ in SECOND_MODES:
            dm.addAction(a["second_" + k])
            g.addAction(a["second_" + k])
        dm.addAction(a["second_cycle"])
        dm.addSeparator()
        g = QActionGroup(self)
        for k, _ in SECOND_FITS:
            dm.addAction(a["second_fit_" + k])
            g.addAction(a["second_fit_" + k])
        dm.addAction(a["second_fit_cycle"])
        m = mb.addMenu("&Bild")
        for k in ("edit", "approve", "edit_del", "edit_clear", "edit_undo", "edit_redo", "edit_reset", None,
                  "order_pick", "order_auto", "order_xy", None, "auto_color", None, "bg_color", "bg_auto"):
            m.addSeparator() if k is None else m.addAction(a[k])
        self.bm_menu = mb.addMenu("B&okmärken")
        self.bm_menu.aboutToShow.connect(self._fill_bookmarks)
        m = mb.addMenu("&Inställningar")
        m.addAction(a["options"])
        m = mb.addMenu("&Hjälp")
        for k in ("help", "about"):
            m.addAction(a[k])
        self.menus = [x.menu() for x in mb.actions()]
        mb.setVisible(self.state.setting("menubar", True))

    def _fill_recent(self):
        self.recent_menu.clear()
        self._recent_into(self.recent_menu)

    def _recent_into(self, m):
        hist = self.state.history()
        if not hist:
            m.addAction("(tom)").setEnabled(False)
        for h in hist:
            c = self.state.comic(h)
            pos = f"   s. {c.get('page', 0) + 1}" + (f"/{c['pages']}" if c.get("pages") else "")
            m.addAction(Path(h).name + pos, lambda h=h: self.v.open(h)).setToolTip(h)
        m.addSeparator()
        m.addAction(self.acts["history"])

    def _fill_bookmarks(self):
        m = self.bm_menu
        m.clear()
        m.addAction(self.acts["bm_add"])
        m.addAction(self.acts["bm_manage"])
        bms = self.state.bookmarks()
        if bms:
            m.addSeparator()
        for b in bms[-15:][::-1]:
            m.addAction(f"{b['name']}  —  {Path(b['path']).name} s. {b['page'] + 1}", lambda b=b: self.open_bookmark(b))

    def _sync(self):
        for a in self.acts.values():
            c = a.property("check")
            if c is not None:
                a.setChecked(bool(c()))
        has = self.v.comic is not None
        for k in ("save_page", "copy_page", "print", "close_file", "next_file", "prev_file", "goto", "thumbs",
                  "slideshow", "bm_add", "rtl"):
            self.acts[k].setEnabled(has)
        self.setWindowTitle(f"PanelView – {self.v.comic.title}" if has else "PanelView")
        self.v.help_text = self.help_text()

    def _context(self, pos):
        """Högerklicksmeny som i ett vanligt Windows-program: vanligaste kommandona först, sedan undermenyer."""
        a = self.acts
        m = QMenu(self)
        for k in ("browse", "open_file", "open_folder"):
            m.addAction(a[k])
        self._recent_into(m.addMenu("Öppna senaste"))
        m.addSeparator()
        for k in ("next_file", "prev_file", "goto", "thumbbar", "slider"):
            m.addAction(a[k])
        m.addSeparator()
        m.addMenu(self.slideshow_menu())
        m.addSeparator()
        for k in ("fullscreen", "guided", "rtl", "double"):
            m.addAction(a[k])
        for sub in self.menus:
            if sub.title().replace("&", "") in ("Visa", "Bild", "Bokmärken"):
                m.addMenu(sub)
        m.addSeparator()
        m.addAction(a["options"])
        m.addAction(a["help"])
        m.addSeparator()
        m.addAction(a["exit"])
        m.exec(pos.toPoint())

    def slideshow_menu(self, m=None):
        """Bildspel: start/stopp, tid i millisekunder, läge och nästa fil."""
        v = self.v
        m = m or QMenu("Bildspel", self)
        m.addAction(self.acts["slideshow"])
        m.addSeparator()
        cur = int(v.opt("slideshow_ms"))
        g = QActionGroup(m)
        for k in ("slide_longer", "slide_shorter"):
            m.addAction(self.acts[k])
        m.addSeparator()
        for ms in SLIDE_STEPS:
            act = m.addAction(f"{ms} ms", lambda ms=ms: self.set_slide_ms(ms))
            act.setCheckable(True)
            act.setChecked(ms == cur)
            g.addAction(act)
        custom = m.addAction(f"Egen tid… ({cur} ms)" if cur not in SLIDE_STEPS
                             else "Egen tid…", self.ask_slide_ms)
        custom.setCheckable(True)
        custom.setChecked(not any(x.isChecked() for x in g.actions()))
        m.addSeparator()
        g2 = QActionGroup(m)
        for mode, label in (("guided", "Ruta för ruta (i guidat läge)"), ("pages", "Sida för sida")):
            act = m.addAction(label, lambda mode=mode: v.set_opt("slideshow_mode", mode))
            act.setCheckable(True)
            act.setChecked(v.opt("slideshow_mode") == mode)
            g2.addAction(act)
        m.addSeparator()
        nf = m.addAction("Fortsätt med nästa fil i mappen", lambda: v.set_opt("slideshow_next_file", not v.opt("slideshow_next_file")))
        nf.setCheckable(True)
        nf.setChecked(bool(v.opt("slideshow_next_file")))
        return m

    def set_slide_ms(self, ms):
        self.v.set_opt("slideshow_ms", int(ms))
        self.v.flash(f"Bildspel: {int(ms)} ms per steg")

    def slide_ms_step(self, d):
        """Nästa längre (d=1) eller kortare (d=-1) tid i SLIDE_STEPS, räknat från nuvarande tid."""
        cur = int(self.v.opt("slideshow_ms"))
        if d > 0:
            ms = next((s for s in SLIDE_STEPS if s > cur), SLIDE_STEPS[-1])
        else:
            ms = next((s for s in reversed(SLIDE_STEPS) if s < cur), SLIDE_STEPS[0])
        self.set_slide_ms(ms)
        self.v.flash(f"Bildspel: {ms / 1000:g} s per steg")

    def ask_slide_ms(self):
        ms, ok = QInputDialog.getInt(self, "Bildspel", "Tid per steg (millisekunder):",
                                     int(self.v.opt("slideshow_ms")), 100, 600000, 100)
        if ok:
            self.set_slide_ms(ms)

    # ---------- arkiv ----------
    def _start_dir(self):
        if self.v.comic:
            return str(self.v.comic.path.parent)
        h = self.state.history()
        return str(Path(h[0]).parent) if h else str(Path.home())

    def open_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "Öppna serie", self._start_dir(), FILTER)
        if p:
            self.v.open(p)

    def open_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Öppna seriemapp", self._start_dir())
        if p:
            self.v.open(p)

    def browse(self):
        from .browser import BrowserDialog
        d = BrowserDialog(self, self.state, self._start_dir())
        if d.exec() == QDialog.DialogCode.Accepted and d.choice:
            if self.v.open(d.choice) and d.page is not None:
                self.v.goto_page(d.page, animate=False)  # vald i sidrutnätet

    def show_history(self):
        HistoryDialog(self).exec()

    def resume_last(self):
        last = self.state.d.get("last")
        if last and Path(last).exists():
            self.v.open(last)
        else:
            self.v.flash("Ingen tidigare serie")

    def _ask_password(self, path):
        pw, ok = QInputDialog.getText(self, "Lösenord", f"Lösenord för {Path(path).name}:", QLineEdit.EchoMode.Password)
        if ok and pw:
            self.v.open(path, password=pw)

    def _finished(self):
        if self.v.opt("auto_next_file"):
            self.v.sibling(1)
        else:
            self.v.flash("Slut på serien")

    def save_page(self):
        data, name = self.v.current_image()
        if data is None:
            return
        p, _ = QFileDialog.getSaveFileName(self, "Spara sida", str(Path(self._start_dir()) / name))
        if p:
            Path(p).write_bytes(data)
            self.v.flash(f"Sparad: {Path(p).name}")

    def copy_page(self):
        sp = self.v._spread(self.v.sp) if self.v.comic else None
        if sp:
            QGuiApplication.clipboard().setImage(sp[0])
            self.v.flash("Sidan kopierad")

    def print_page(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        sp = self.v._spread(self.v.sp) if self.v.comic else None
        if not sp:
            return
        pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(pr, self).exec() != QDialog.DialogCode.Accepted:
            return
        img = sp[0]
        p = QPainter(pr)
        r = pr.pageRect(QPrinter.Unit.DevicePixel)
        s = min(r.width() / img.width(), r.height() / img.height())
        p.drawImage(QRectF((r.width() - img.width() * s) / 2, (r.height() - img.height() * s) / 2,
                           img.width() * s, img.height() * s), img)
        p.end()

    def clear_history(self):
        self.state.clear_history()
        self.v.flash("Historiken rensad")

    # ---------- visa ----------
    UI_SCALES = (0.75, 0.9, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)

    def ui_scale_step(self, d):
        cur = self.v.base_ui_scale()
        i = min(range(len(self.UI_SCALES)), key=lambda j: abs(self.UI_SCALES[j] - cur))
        val = self.UI_SCALES[max(0, min(len(self.UI_SCALES) - 1, i + d))]
        self.v.set_opt("ui_scale", val)
        self.apply_ui_scale()
        self.v.flash(f"Gränssnittets storlek {int(val * 100)} %"
                     + (f" (× {self.v.opt('distance_ui_scale'):g} i avståndsläget)" if self.v.opt("distance_mode") else ""))

    def apply_ui_scale(self):
        """Menyer, dialoger och listor följer ui_scale (visningens text skalas i Viewer)."""
        app = QApplication.instance()
        if not hasattr(self, "_base_font"):
            self._base_font = QFont(app.font())
        f = QFont(self._base_font)
        f.setPointSizeF(max(6.0, self._base_font.pointSizeF() * self.v.ui_scale()))
        app.setFont(f)
        for w in (self.menuBar(), getattr(self, "top_bar", None)):
            if w is not None:
                w.setFont(f)
        self.v.thumbbar.set_scale(self.v.ui_scale())
        self.v.slider.set_scale(self.v.ui_scale())
        self.v.update()

    def _toggle(self, k):
        self.v.set_opt(k, not self.v.opt(k))
        self.v.flash(f"{self._label_for(k)}: {'på' if self.v.opt(k) else 'av'}")

    def _label_for(self, k):
        a = self.acts.get(k)
        return a.text().replace("&", "") if a else k

    def fit_of(self, side):
        """Anpassningen för vänster/höger skärm i aktuellt läge (spegling har egna värden)."""
        return self.state.setting(fit_key(side, self.second.mode), "screen")

    def set_fit(self, fit, zoom=1.0, side=None):
        """side: 'left'/'right' (fysisk skärm); None = huvudfönstrets skärm."""
        side = side or side_of(self)
        if fit == "original":
            self.v.state.set_setting("zoom", zoom)
        self.v.set_opt(fit_key(side, self.second.mode), fit)
        self.second.update()
        label = dict(FITS)[fit] if fit != "original" or zoom == 1.0 else f"Zoom {int(zoom * 100)} %"
        self.v.flash(f"{dict(SIDES)[side]}: {label[0].lower()}{label[1:]}")

    def rotate(self, d):
        self.v.set_opt("rotation", (self.v.opt("rotation") + d) % 360)
        self.v.flash(f"Rotation {self.v.opt('rotation')}°")

    def toggle_fullscreen(self):
        self.top_bar.hide()
        if self.isFullScreen():
            self.showNormal()
            self.menuBar().setVisible(self.state.setting("menubar", True))
        else:
            self.menuBar().setVisible(False)
            self.showFullScreen()
        self.state.set_setting("fullscreen", self.isFullScreen())
        self._sync()

    def set_second(self, mode, save=True):
        before = self.v.fit()
        msg = self.second.set_mode(mode)
        if self.v.fit() != before:  # spegling har egna anpassningar
            self.v.refit()
        if save:
            self.state.set_setting("second_screen", self.second.mode)
        label = dict(SECOND_MODES)[self.second.mode]
        self.v.flash(msg or f"Andra skärmen: {label}")
        self._sync()

    def cycle_second(self):
        keys = [k for k, _ in SECOND_MODES]
        self.set_second(keys[(keys.index(self.second.mode) + 1) % len(keys)])

    def set_second_fit(self, fit):
        self.state.set_setting(fit_key(self.second.side(), self.second.mode), fit)
        self.second.update()
        self.v.flash(dict(SECOND_FITS)[fit])
        self._sync()

    def cycle_second_fit(self):
        keys = [k for k, _ in SECOND_FITS]
        cur = self.second.fit()
        self.set_second_fit(keys[(keys.index(cur) + 1) % len(keys)] if cur in keys else keys[0])

    def _screen_moved(self, _scr):
        """Huvudfönstret flyttat till en annan skärm: andra skärmen flyttar till en skärm som inte är huvudfönstrets."""
        if self.second.mode != "off":
            self.second.relocate()
        self.v.refit()  # ny sida (vänster/höger) -> den sidans anpassning

    def toggle_menubar(self):
        on = not self.state.setting("menubar", True)
        self.state.set_setting("menubar", on)
        if not self.isFullScreen():
            self.menuBar().setVisible(on)
        self._sync()

    def toggle_info(self):
        self.v.hud_always = not self.v.hud_always
        self.v.update()
        self._sync()

    def toggle_help(self):
        self.v.show_help = not self.v.show_help
        self.v.update()
        self._sync()

    def nav(self, d, arrow=False):
        """Pilar/mellanslag stegar alltid genom rutorna, även med miniatyrlist eller reglage öppna."""
        self.v.step(d)  # miniatyrlisten/reglaget är öppna samtidigt och följer med

    def enter(self):
        self.toggle_fullscreen()

    def escape(self):
        if self.v.order_pick is not None:
            self.v.toggle_order()
        elif self.v.thumbbar.isVisible():
            self.v.toggle_thumbbar()
        elif self.v.show_help:
            self.toggle_help()
        elif self.v.slideshow.isActive():
            self.v.toggle_slideshow()
        elif self.isFullScreen():
            self.toggle_fullscreen()
            self._left_full = time.monotonic()
        elif time.monotonic() - self._left_full < 1.0:
            pass  # andra Esc direkt efter att helskärmen lämnats: aldrig avsluta av misstag
        elif self.v.opt("esc_quit") == "direct":
            self.close()
        elif self.v.opt("esc_quit") == "confirm":
            if QMessageBox.question(self, "Avsluta", "Avsluta PanelView?") == QMessageBox.StandardButton.Yes:
                self.close()
        else:
            self.v.flash("Esc avslutar inte – Ctrl+Q avslutar (ändras i Inställningar → Läsning)")

    def pick_bg(self):
        cur = self.v.opt("bg")
        c = QColorDialog.getColor(QColor("#0c0c0c" if cur == "auto" else cur), self, "Bakgrundsfärg")
        if c.isValid():
            self.v.set_opt("bg", c.name())
            self.v.sp_cache.clear()
            self.v.update()

    def toggle_bg_auto(self):
        self.v.set_opt("bg", "#0c0c0c" if self.v.opt("bg") == "auto" else "auto")
        self.v.sp_cache.clear()
        self.v.goto_page(self.v.page, animate=False)

    def goto_dialog(self):
        if not self.v.comic:
            return
        n, ok = QInputDialog.getInt(self, "Gå till sida", "Sida:", self.v.page + 1, 1, len(self.v.comic.pages))
        if ok:
            self.v.goto_page(n - 1)

    def thumbnails(self):
        if self.v.comic:
            d = ThumbDialog(self, self.v)
            if d.exec() == QDialog.DialogCode.Accepted and d.choice is not None:
                self.v.goto_page(d.choice)

    # ---------- bokmärken ----------
    def add_bookmark(self):
        if not self.v.comic:
            return
        name, ok = QInputDialog.getText(self, "Bokmärke", "Namn:",
                                        text=f"{self.v.comic.title} s. {self.v.page + 1}")
        if ok:
            self.state.add_bookmark(self.v.comic.path, self.v.page, name or "Bokmärke")
            self.v.flash("Bokmärke sparat")

    def open_bookmark(self, b):
        if not Path(b["path"]).exists():
            self.v.flash("Filen finns inte längre")
            return
        if not self.v.comic or self.v.comic.path != Path(b["path"]):
            if not self.v.open(b["path"]):
                return
        self.v.goto_page(b["page"], animate=False)

    def manage_bookmarks(self):
        BookmarkDialog(self).exec()

    # ---------- inställningar / hjälp ----------
    def options(self):
        if OptionsDialog(self).exec() == QDialog.DialogCode.Accepted:
            self._apply_keys()
            self._sync()

    def help_text(self):
        rows = []
        for k, a in self.acts.items():
            ks = [s.toString(QKeySequence.SequenceFormat.NativeText) for s in a.shortcuts()]
            if ks:
                rows.append(f"{' / '.join(ks):<26}{a.text().replace('&', '')}")
        rows += ["", "Dubbelklick                zooma till rutan under musen (igen = hela sidan)",
                 "Klick vänster/höger kant   föregående / nästa",
                 "Ctrl+hjul / dra            fri zoom / panorera",
                 "Mittenknapp (håll)         förstoringsglas",
                 "Högerklick                 meny",
                 "Musknappar bakåt/framåt    föregående / nästa fil"]
        return "PanelView – kortkommandon\n\n" + "\n".join(rows)

    def about(self):
        QMessageBox.about(self, "Om PanelView",
                          f"<b>PanelView {__version__}</b><br>Serieläsare med automatisk zoom ruta för ruta.<br><br>"
                          "Rutdetektering: cbxy (MIT) och YOLO-modellen mosesb/best-comic-panel-detection (Apache-2.0)"
                          " via ONNX Runtime.<br>Gränssnitt: Qt / PySide6 (LGPL). PDF: pdfium (BSD/Apache).")

    # ---------- fönster ----------
    def _restore_geometry(self):
        g = self.state.setting("geometry")
        if g:
            self.restoreGeometry(QByteArray.fromBase64(g.encode()))

    def show_initial(self, force_full=False):
        if force_full or self.state.setting("fullscreen", False):
            self.menuBar().setVisible(False)
            self.showFullScreen()
        else:
            self.show()
        self.windowHandle().screenChanged.connect(self._screen_moved)
        mode = self.state.setting("second_screen", "off")
        if mode != "off":  # efter att huvudfönstret hamnat på sin skärm
            QTimer.singleShot(0, lambda: self.set_second(mode, save=False))
        self._sync()

    def keyPressEvent(self, e):
        super().keyPressEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self.v.open(urls[0].toLocalFile())

    def closeEvent(self, e):
        if not self.isFullScreen():
            self.state.set_setting("geometry", bytes(self.saveGeometry().toBase64()).decode())
        self.persist.stop()
        self.second.close()
        self.v.close_comic()
        if self.v.opt("clear_history_on_exit"):
            self.state.clear_history()
        self.state.save()
        super().closeEvent(e)


class _ThumbSig(QObject):
    done = Signal(int, QImage)


class _Thumb(QRunnable):
    def __init__(self, comic, i, sig, size):
        super().__init__()
        self.comic, self.i, self.sig, self.size = comic, i, sig, size

    def run(self):
        try:
            img = QImage.fromData(self.comic.read(self.i))
            img = img.scaled(self.size, self.size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        except Exception:
            img = QImage()
        try:
            self.sig.done.emit(self.i, img)
        except RuntimeError:
            pass


class ThumbDialog(QDialog):
    SIZE = 180

    def __init__(self, parent, viewer):
        super().__init__(parent)
        self.setWindowTitle(f"Miniatyrer – {viewer.comic.title}")
        self.resize(1100, 760)
        self.choice = None
        self.list = QListWidget(viewMode=QListWidget.ViewMode.IconMode, resizeMode=QListWidget.ResizeMode.Adjust,
                                movement=QListWidget.Movement.Static, uniformItemSizes=True)
        self.list.setIconSize(QSize(self.SIZE, self.SIZE))
        self.list.setGridSize(QSize(self.SIZE + 16, self.SIZE + 34))
        self.list.itemActivated.connect(self._pick)
        self.bar = Progress("Miniatyrer")
        self.done_n = 0
        lay = QVBoxLayout(self)
        lay.addWidget(self.list)
        lay.addWidget(self.bar)
        self.sig = _ThumbSig(self)
        self.sig.done.connect(self._done)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        ph = QPixmap(self.SIZE, self.SIZE)
        ph.fill(QColor(50, 50, 50))
        n = len(viewer.comic.pages)
        order = sorted(range(n), key=lambda i: abs(i - viewer.page))  # närmast aktuell sida först
        for i in range(n):
            it = QListWidgetItem(QIcon(ph), str(i + 1))
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.list.addItem(it)
        self.bar.tick(0, n)
        for i in order:
            self.pool.start(_Thumb(viewer.comic, i, self.sig, self.SIZE))
        self.list.setCurrentRow(viewer.page)
        self.list.scrollToItem(self.list.currentItem())

    def _done(self, i, img):
        self.done_n += 1
        self.bar.tick(self.done_n, self.list.count())
        if not img.isNull():
            self.list.item(i).setIcon(QIcon(QPixmap.fromImage(img)))

    def _pick(self, it):
        self.choice = it.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def done(self, r):
        self.pool.clear()
        self.pool.waitForDone(2000)
        super().done(r)


class HistoryDialog(QDialog):
    """De senast öppnade serierna (upp till 20) med var man var, när de öppnades och var de ligger."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Visningshistorik")
        self.resize(900, 520)
        self.t = QTableWidget(0, 4)
        self.t.setHorizontalHeaderLabels(["Serie", "Position", "Senast öppnad", "Mapp"])
        self.t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.t.verticalHeader().hide()
        h = self.t.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.t.setColumnWidth(3, 280)
        self.t.cellDoubleClicked.connect(lambda *_: self._go())
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Dubbelklicka eller tryck Enter för att fortsätta där du var."))
        lay.addWidget(self.t)
        row = QHBoxLayout()
        for label, fn in (("Öppna", self._go), ("Ta bort", self._rm), ("Rensa allt", self._clear)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        close = QPushButton("Stäng")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)
        self._fill()

    def _fill(self):
        st = self.win.state
        self.paths = st.history()
        self.t.setRowCount(len(self.paths))
        for r, p in enumerate(self.paths):
            c = st.comic(p)
            pos = f"sida {c.get('page', 0) + 1}" + (f" av {c['pages']}" if c.get("pages") else "")
            if c.get("panel"):
                pos += f", ruta {c['panel'] + 1}"
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(c["opened"])) if c.get("opened") else ""
            for col, txt in enumerate((Path(p).name, pos, when, str(Path(p).parent))):
                it = QTableWidgetItem(txt)
                it.setToolTip(p)
                self.t.setItem(r, col, it)
        if self.paths:
            self.t.selectRow(0)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._go()
        elif e.key() == Qt.Key.Key_Delete:
            self._rm()
        else:
            super().keyPressEvent(e)

    def _go(self):
        r = self.t.currentRow()
        if 0 <= r < len(self.paths):
            self.accept()
            self.win.v.open(self.paths[r])

    def _rm(self):
        r = self.t.currentRow()
        if 0 <= r < len(self.paths):
            st = self.win.state
            st.d["history"] = [h for h in st.d.get("history", []) if h != self.paths[r]]
            st.save()
            self._fill()

    def _clear(self):
        self.win.clear_history()
        self._fill()


class BookmarkDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Bokmärken")
        self.resize(640, 420)
        self.list = QListWidget()
        self.list.itemActivated.connect(lambda _: self._go())
        go, rm, rn = QPushButton("Gå till"), QPushButton("Ta bort"), QPushButton("Byt namn…")
        go.clicked.connect(self._go)
        rm.clicked.connect(self._rm)
        rn.clicked.connect(self._rename)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        row = QHBoxLayout()
        for b in (go, rn, rm):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(bb)
        lay = QVBoxLayout(self)
        lay.addWidget(self.list)
        lay.addLayout(row)
        self._fill()

    def _fill(self):
        self.list.clear()
        for b in self.win.state.bookmarks():
            self.list.addItem(f"{b['name']}   —   {Path(b['path']).name}, sida {b['page'] + 1}")

    def _go(self):
        i = self.list.currentRow()
        if i >= 0:
            self.win.open_bookmark(self.win.state.bookmarks()[i])
            self.accept()

    def _rm(self):
        i = self.list.currentRow()
        if i >= 0:
            self.win.state.remove_bookmark(i)
            self._fill()

    def _rename(self):
        i = self.list.currentRow()
        if i < 0:
            return
        b = self.win.state.bookmarks()[i]
        name, ok = QInputDialog.getText(self, "Byt namn", "Namn:", text=b["name"])
        if ok and name:
            b["name"] = name
            self.win.state.save()
            self._fill()


class OptionsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.v = win, win.v
        self.setWindowTitle("Inställningar")
        self.resize(720, 620)
        tabs = QTabWidget()
        self.w = {}

        def chk(k, label):
            c = QCheckBox(label)
            c.setChecked(bool(self.v.opt(k)))
            self.w[k] = (c, lambda c=c: c.isChecked())
            return c

        def combo(k, items):
            c = QComboBox()
            for val, label in items:
                c.addItem(label, val)
            c.setCurrentIndex(max(0, c.findData(self.v.opt(k))))
            self.w[k] = (c, lambda c=c: c.currentData())
            return c

        def num(k, lo, hi, step=1.0, dec=0, suffix=""):
            c = QDoubleSpinBox(decimals=dec, minimum=lo, maximum=hi, singleStep=step, suffix=suffix)
            c.setValue(float(self.v.opt(k)))
            self.w[k] = (c, (lambda c=c: c.value()) if dec else (lambda c=c: int(c.value())))
            return c

        # Visning
        t = QWidget()
        f = QFormLayout(t)
        self.bg_btn = QPushButton()
        self.bg_val = self.v.opt("bg")
        self._bg_label()
        self.bg_btn.clicked.connect(self._pick_bg)
        f.addRow("Bakgrundsfärg", self.bg_btn)
        f.addRow("Skalning", combo("quality", [("fast", "Snabb (närmaste)"), ("smooth", "Jämn (utom under animering)"),
                                              ("best", "Bästa (alltid jämn)")]))
        f.addRow(chk("anim", "Animerad zoom mellan rutor"))
        f.addRow("Animationstid", num("anim_ms", 50, 2000, 10, 0, " ms"))
        f.addRow(QLabel("<b>Anpassa till skärm</b> (som CDisplayEx)"))
        f.addRow(chk("shrink_w", "Krymp bilder som är bredare än skärmen"))
        f.addRow(chk("grow_w", "Förstora bilder som är smalare än skärmen"))
        f.addRow(chk("shrink_h", "Krymp bilder som är högre än skärmen"))
        f.addRow(chk("grow_h", "Förstora bilder som är lägre än skärmen"))
        f.addRow(chk("dim", "Svart runt aktuell ruta"))
        f.addRow(chk("show_pagenum", "Visa sidnummer"))
        f.addRow(chk("show_progress", "Visa förloppslist"))
        f.addRow(chk("hide_cursor", "Dölj muspekaren i helskärm"))
        f.addRow(QLabel("<b>Storlek och avstånd</b>"))
        f.addRow("Gränssnittets storlek (text, listor, menyer)", num("ui_scale", 0.5, 4.0, 0.05, 2, " ×"))
        f.addRow(chk("distance_mode", "Avståndsläge (Shift+F)"))
        f.addRow("  Sidräknarens storlek i avståndsläget", num("distance_scale", 1.0, 10.0, 0.25, 2, " ×"))
        f.addRow("  Övrigt gränssnitt i avståndsläget", num("distance_ui_scale", 1.0, 4.0, 0.1, 2, " ×"))
        f.addRow(chk("counter_autohide", "Dölj sidräknaren vid inaktivitet även utanför avståndsläget"))
        f.addRow("  Döljs efter", num("counter_hide_ms", 300, 10000, 100, 0, " ms"))
        tabs.addTab(t, "Visning")
        # Läsning
        t = QWidget()
        f = QFormLayout(t)
        f.addRow(chk("guided", "Guidat läge: zooma ruta för ruta"))
        f.addRow(chk("overview", "Visa hela sidan innan rutorna"))
        fits = list(FITS) + [("main", "Samma utsnitt som huvudfönstret (bara andra skärmen)")]
        mode = "spegling" if win.second.mode == "mirror" else "av/fördelning"
        for side, label in SIDES:
            f.addRow(f"Anpassning, {label.lower()} ({mode})", combo(fit_key(side, win.second.mode), fits))
        f.addRow(chk("double", "Dubbelsida"))
        f.addRow(chk("cover_single", "Omslaget visas ensamt i dubbelsidesläge"))
        f.addRow(chk("shadow", "Skugga i bokryggen"))
        f.addRow(chk("auto_next_file", "Öppna nästa fil i mappen vid slutet"))
        f.addRow("Bildspel, tid per steg", num("slideshow_ms", 100, 600000, 100, 0, " ms"))
        f.addRow("Bildspel, läge", combo("slideshow_mode", [("guided", "Ruta för ruta (i guidat läge)"),
                                                            ("pages", "Sida för sida")]))
        f.addRow(chk("slideshow_next_file", "Bildspelet fortsätter med nästa fil i mappen"))
        f.addRow("Sortering", combo("sort", [("natural", "Naturlig (2 före 10)"), ("alpha", "Alfabetisk")]))
        f.addRow(QLabel("<b>Avslutning</b>"))
        f.addRow("Esc när helskärm och fönster redan är stängda",
                 combo("esc_quit", [("never", "Avsluta inte (Ctrl+Q avslutar)"), ("confirm", "Fråga först"),
                                    ("direct", "Avsluta direkt")]))
        tabs.addTab(t, "Läsning")
        # Bild
        t = QWidget()
        f = QFormLayout(t)
        f.addRow(chk("auto_color", "Automatisk färgkorrigering (vitbalans + kontrast)"))
        f.addRow("Gamma", num("gamma", 0.3, 3.0, 0.05, 2))
        f.addRow("Lyster (vibrance)", num("vibrance", 0.0, 1.5, 0.05, 2))
        f.addRow("Rotation", combo("rotation", [(0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")]))
        f.addRow("Förstoringsglas, form", combo("mag_shape", list(MAG_SHAPES)))
        f.addRow("Förstoringsglas, bredd", num("mag_size", 80, 1600, 20, 0, " px"))
        f.addRow("Rektangel, höjd/bredd", num("mag_aspect", 0.2, 2.0, 0.05, 2))
        f.addRow("Förstoringsglas, förstoring", num("mag_zoom", 1.25, 8.0, 0.25, 2, " ×"))
        f.addRow("Lins, förvrängning", num("mag_warp", 0.0, 1.5, 0.1, 2))
        tabs.addTab(t, "Bild")
        # Historik
        t = QWidget()
        f = QFormLayout(t)
        f.addRow(chk("history", "Spara historik"))
        f.addRow(chk("clear_history_on_exit", "Rensa historiken när programmet stängs"))
        b = QPushButton("Rensa historik nu")
        b.clicked.connect(win.clear_history)
        f.addRow(b)
        tabs.addTab(t, "Historik")
        # Tangenter
        t = QWidget()
        lay = QVBoxLayout(t)
        self.keys = QTableWidget(len(win.acts), 3)
        self.keys.setHorizontalHeaderLabels(["Funktion", "Genväg", "Sekundär genväg"])
        self.keys.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.key_edits = {}
        for r, (k, a) in enumerate(win.acts.items()):
            self.keys.setCellWidget(r, 0, QLabel(a.text()))
            sc = [s.toString() for s in a.shortcuts()]
            e1 = QKeySequenceEdit(QKeySequence(sc[0] if sc else ""))
            e2 = QKeySequenceEdit(QKeySequence(sc[1] if len(sc) > 1 else ""))
            self.keys.setCellWidget(r, 1, e1)
            self.keys.setCellWidget(r, 2, e2)
            self.key_edits[k] = (e1, e2, sc[2:])
        lay.addWidget(self.keys)
        rb = QPushButton("Återställ standardgenvägar")
        rb.clicked.connect(self._reset_keys)
        lay.addWidget(rb)
        tabs.addTab(t, "Tangenter")

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)

    def _bg_label(self):
        self.bg_btn.setText("Automatisk (kantfärg)" if self.bg_val == "auto" else self.bg_val)

    def _pick_bg(self):
        m = QMenu(self)
        m.addAction("Automatisk (sidans kantfärg)", lambda: setattr(self, "bg_val", "auto"))
        m.addAction("Välj färg…", self._color)
        m.exec(self.bg_btn.mapToGlobal(self.bg_btn.rect().bottomLeft()))
        self._bg_label()

    def _color(self):
        c = QColorDialog.getColor(QColor("#0c0c0c" if self.bg_val == "auto" else self.bg_val), self)
        if c.isValid():
            self.bg_val = c.name()

    def _reset_keys(self):
        self.win.state.d["keys"] = {}
        for k, (e1, e2, _rest) in self.key_edits.items():
            d = self.win.acts[k].property("default_keys")
            e1.setKeySequence(QKeySequence(d[0] if d else ""))
            e2.setKeySequence(QKeySequence(d[1] if len(d) > 1 else ""))

    def _save(self):
        changed = {}
        for k, (wd, get) in self.w.items():
            val = get()
            if val != self.v.opt(k):
                changed[k] = val
        if self.bg_val != self.v.opt("bg"):
            changed["bg"] = self.bg_val
        for k, val in changed.items():
            self.v.state.set_setting(k, val)
        if "anim_ms" in changed:
            self.v.anim.setDuration(int(changed["anim_ms"]))
        if changed.keys() & {"ui_scale", "distance_mode", "distance_ui_scale"}:
            self.win.apply_ui_scale()
        if self.v.comic:
            if "sort" in changed:
                self.v.open(self.v.comic.path)
            elif changed.keys() & {"rotation", "auto_color", "gamma", "vibrance"}:
                self.v.reload_images()
            else:
                self.v.sp_cache.clear()
                self.v._layout(keep_page=True)
        for k, (e1, e2, rest) in self.key_edits.items():
            seqs = [e1.keySequence().toString(), e2.keySequence().toString()] + rest
            seqs = [s for s in seqs if s]
            default = self.win.acts[k].property("default_keys")
            cur = [s.toString() for s in self.win.acts[k].shortcuts()]
            if seqs != cur:
                self.win.state.set_keys(k, seqs)
            elif k in self.win.state.keys() and seqs == default:
                del self.win.state.keys()[k]
        self.win.state.save()
        self.v.goto_page(self.v.page, animate=False)
        self.accept()
