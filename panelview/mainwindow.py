"""Huvudfönster: menyer, kortkommandon (ändringsbara), dialoger för inställningar, bokmärken, miniatyrer och utskrift.

Funktionsuppsättningen följer CDisplayEx (se FEATURES.md) plus PanelViews guidade rutzoom.
"""
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QRunnable, QSize, Qt, QThreadPool, QObject, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QKeySequenceEdit,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSpinBox, QTableWidget, QTabWidget, QVBoxLayout, QWidget)

from . import __version__
from .comic import ARCHIVE_EXT, IMAGE_EXT
from .store import State
from .viewer import DEFAULTS, Viewer

FILTER = "Serier och bilder ({});;Alla filer (*)".format(
    " ".join(f"*{e}" for e in sorted(ARCHIVE_EXT | set(IMAGE_EXT))))

FITS = [("screen", "Anpassa till skärm"), ("width", "Anpassa till bredd"), ("height", "Anpassa till höjd"),
        ("original", "Originalstorlek (100 %)")]
ZOOMS = [1.25, 1.5, 2.0, 4.0]


class MainWindow(QMainWindow):
    def __init__(self, path=None):
        super().__init__()
        self.state = State()
        self.v = Viewer(self.state)
        self.setCentralWidget(self.v)
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
        if path:
            self.v.open(path)
        elif self.v.opt("resume_on_start"):
            self.resume_last()

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
        for i, (k, label) in enumerate(FITS):
            A("fit_" + k, label, [str(i + 1)], lambda k=k: self.set_fit(k), check=lambda k=k: v.opt("fit") == k and (k != "original" or v.opt("zoom") == 1.0))
        for z in ZOOMS:
            A(f"zoom_{int(z * 100)}", f"Zoom {int(z * 100)} %", [], lambda z=z: self.set_fit("original", z),
              check=lambda z=z: v.opt("fit") == "original" and v.opt("zoom") == z)
        for k, label in (("shrink_w", "Krymp bilder bredare än skärmen"), ("grow_w", "Förstora bilder smalare än skärmen"),
                         ("shrink_h", "Krymp bilder högre än skärmen"), ("grow_h", "Förstora bilder lägre än skärmen")):
            A(k, label, [], lambda k=k: self._toggle(k), check=lambda k=k: v.opt(k))
        A("zoom_in", "Zooma in", ["+", "=", "Ctrl++"], lambda: v.zoom(1.25))
        A("zoom_out", "Zooma ut", ["-", "Ctrl+-"], lambda: v.zoom(0.8))
        A("zoom_reset", "Återställ zoom", ["0"], v.reset_zoom)
        A("rot_left", "Rotera vänster", ["["], lambda: self.rotate(-90))
        A("rot_right", "Rotera höger", ["]"], lambda: self.rotate(90))
        A("magnifier", "Förstoringsglas (eller håll mittenknappen)", ["M"], v.toggle_magnifier, check=lambda: v.mag_on)
        A("info", "Informationsrad alltid", ["I"], self.toggle_info, check=lambda: v.hud_always)
        A("pagenum", "Sidnummer", [], lambda: self._toggle("show_pagenum"), check=lambda: v.opt("show_pagenum"))
        A("progress", "Förloppslist (klickbar)", [], lambda: self._toggle("show_progress"), check=lambda: v.opt("show_progress"))
        # Bild
        A("auto_color", "Automatisk färgkorrigering", ["A"], lambda: self._toggle("auto_color"), check=lambda: v.opt("auto_color"))
        A("bg_color", "Bakgrundsfärg…", [], self.pick_bg)
        A("bg_auto", "Automatisk bakgrundsfärg", [], self.toggle_bg_auto, check=lambda: v.opt("bg") == "auto")
        # Bokmärken
        A("edit", "Redigera rutor (rita/ta bort, sparas)", ["E"], v.toggle_edit, check=lambda: v.edit)
        A("edit_del", "Ta bort rutan under musen", ["Delete"], v.edit_delete_under_mouse)
        A("edit_undo", "Ångra rutändring", ["Ctrl+Z"], v.edit_undo_last)
        A("edit_reset", "Automatiska rutor igen (uppslaget)", ["Ctrl+R"], v.edit_reset_page)
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
        for k in ("resume", None, "next_file", "prev_file", None, "save_page", "copy_page", "print", None,
                  "close_file", "clear_history", None, "exit"):
            m.addSeparator() if k is None else m.addAction(a[k])
        m = mb.addMenu("&Navigera")
        for k in ("next", "prev", "right", "left", None, "next_page", "prev_page", "first", "last", "goto", None,
                  "thumbbar", "slider", "thumbs"):
            m.addSeparator() if k is None else m.addAction(a[k])
        sm = m.addMenu("Bildspel")
        sm.aboutToShow.connect(lambda sm=sm: (sm.clear(), self.slideshow_menu(sm)))
        m = mb.addMenu("&Visa")
        for k in ("fullscreen", "menubar", None, "guided", "overview", "dim", None, "rtl", "double", "cover_single",
                  "shadow"):
            m.addSeparator() if k is None else m.addAction(a[k])
        fm = m.addMenu("Anpassning")
        g = QActionGroup(self)
        for k, _ in FITS:
            fm.addAction(a["fit_" + k])
            g.addAction(a["fit_" + k])
        fm.addSeparator()
        for z in ZOOMS:
            fm.addAction(a[f"zoom_{int(z * 100)}"])
            g.addAction(a[f"zoom_{int(z * 100)}"])
        fm.addSeparator()
        for k in ("shrink_w", "grow_w", "shrink_h", "grow_h"):
            fm.addAction(a[k])
        for k in (None, "zoom_in", "zoom_out", "zoom_reset", None, "rot_left", "rot_right", None, "magnifier", "info",
                  "pagenum", "progress"):
            m.addSeparator() if k is None else m.addAction(a[k])
        m = mb.addMenu("&Bild")
        for k in ("edit", "edit_del", "edit_undo", "edit_reset", None, "auto_color", None, "bg_color", "bg_auto"):
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
        hist = self.state.history()
        if not hist:
            self.recent_menu.addAction("(tom)").setEnabled(False)
        for h in hist[:15]:
            self.recent_menu.addAction(Path(h).name, lambda h=h: self.v.open(h)).setToolTip(h)

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
        rec = m.addMenu("Öppna senaste")
        self.recent_menu_ctx = rec
        hist = self.state.history()
        for h in hist[:15]:
            rec.addAction(Path(h).name, lambda h=h: self.v.open(h)).setToolTip(h)
        if not hist:
            rec.addAction("(tom)").setEnabled(False)
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
        for ms in (500, 1000, 1500, 2000, 3000, 5000, 8000, 10000, 15000, 30000):
            act = m.addAction(f"{ms} ms", lambda ms=ms: self.set_slide_ms(ms))
            act.setCheckable(True)
            act.setChecked(ms == cur)
            g.addAction(act)
        custom = m.addAction(f"Egen tid… ({cur} ms)" if cur not in (500, 1000, 1500, 2000, 3000, 5000, 8000, 10000, 15000, 30000)
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
            self.v.open(d.choice)

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
    def _toggle(self, k):
        self.v.set_opt(k, not self.v.opt(k))
        self.v.flash(f"{self._label_for(k)}: {'på' if self.v.opt(k) else 'av'}")

    def _label_for(self, k):
        a = self.acts.get(k)
        return a.text().replace("&", "") if a else k

    def set_fit(self, fit, zoom=1.0):
        self.v.state.set_setting("zoom", zoom)
        self.v.set_opt("fit", fit)
        label = dict(FITS)[fit] if fit != "original" or zoom == 1.0 else f"Zoom {int(zoom * 100)} %"
        self.v.flash(label)

    def rotate(self, d):
        self.v.set_opt("rotation", (self.v.opt("rotation") + d) % 360)
        self.v.flash(f"Rotation {self.v.opt('rotation')}°")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.menuBar().setVisible(self.state.setting("menubar", True))
        else:
            self.menuBar().setVisible(False)
            self.showFullScreen()
        self.state.set_setting("fullscreen", self.isFullScreen())
        self._sync()

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
        if self.v.thumbbar.isVisible():
            self.v.toggle_thumbbar()
        elif self.v.show_help:
            self.toggle_help()
        elif self.v.slideshow.isActive():
            self.v.toggle_slideshow()
        elif self.isFullScreen():
            self.toggle_fullscreen()
        else:
            self.close()

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
        lay = QVBoxLayout(self)
        lay.addWidget(self.list)
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
        for i in order:
            self.pool.start(_Thumb(viewer.comic, i, self.sig, self.SIZE))
        self.list.setCurrentRow(viewer.page)
        self.list.scrollToItem(self.list.currentItem())

    def _done(self, i, img):
        if not img.isNull():
            self.list.item(i).setIcon(QIcon(QPixmap.fromImage(img)))

    def _pick(self, it):
        self.choice = it.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def done(self, r):
        self.pool.clear()
        self.pool.waitForDone(2000)
        super().done(r)


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
        tabs.addTab(t, "Visning")
        # Läsning
        t = QWidget()
        f = QFormLayout(t)
        f.addRow(chk("guided", "Guidat läge: zooma ruta för ruta"))
        f.addRow(chk("overview", "Visa hela sidan innan rutorna"))
        f.addRow("Anpassning", combo("fit", FITS))
        f.addRow(chk("double", "Dubbelsida"))
        f.addRow(chk("cover_single", "Omslaget visas ensamt i dubbelsidesläge"))
        f.addRow(chk("shadow", "Skugga i bokryggen"))
        f.addRow(chk("auto_next_file", "Öppna nästa fil i mappen vid slutet"))
        f.addRow("Bildspel, tid per steg", num("slideshow_ms", 100, 600000, 100, 0, " ms"))
        f.addRow("Bildspel, läge", combo("slideshow_mode", [("guided", "Ruta för ruta (i guidat läge)"),
                                                            ("pages", "Sida för sida")]))
        f.addRow(chk("slideshow_next_file", "Bildspelet fortsätter med nästa fil i mappen"))
        f.addRow("Sortering", combo("sort", [("natural", "Naturlig (2 före 10)"), ("alpha", "Alfabetisk")]))
        f.addRow(chk("resume_on_start", "Återuppta senaste serien vid start"))
        tabs.addTab(t, "Läsning")
        # Bild
        t = QWidget()
        f = QFormLayout(t)
        f.addRow(chk("auto_color", "Automatisk färgkorrigering (vitbalans + kontrast)"))
        f.addRow("Gamma", num("gamma", 0.3, 3.0, 0.05, 2))
        f.addRow("Lyster (vibrance)", num("vibrance", 0.0, 1.5, 0.05, 2))
        f.addRow("Rotation", combo("rotation", [(0, "0°"), (90, "90°"), (180, "180°"), (270, "270°")]))
        f.addRow("Förstoringsglas, storlek", num("mag_size", 120, 900, 20, 0, " px"))
        f.addRow("Förstoringsglas, förstoring", num("mag_zoom", 1.25, 6.0, 0.25, 2, " ×"))
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
