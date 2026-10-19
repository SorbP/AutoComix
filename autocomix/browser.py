"""File browser with preview (L): folder tree | file list | preview, with draggable splitters.

The file list uses the system icons and columns (name, size, type, modified) like Explorer. The preview shows
the first page of folders, zip/cbz, pdf and (with 7-Zip) rar/7z, plus the page count. "Show all pages" (P) instead
shows all pages as thumbnails, read directly from the archive without extracting to disk.
"""
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QDir, QIODevice, QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileSystemModel, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QSplitter, QStackedWidget, QStyle, QTreeView,
                               QVBoxLayout, QWidget)

from .i18n import tr
from .overlays import Progress
from .comic import ARCHIVE_EXT, IMAGE_EXT, file_mtime, pick_images, sort_key, zip_mtime

PREVIEW_MAX = 1600
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _seven_zip():
    for exe in ("7z", r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if shutil.which(exe) or Path(exe).exists():
            return exe
    return None


class PageSource:
    """The pages of a comic without extracting anything to disk: folder, zip/cbz and pdf are read page by page,
    rar/7z are streamed through 7-Zip (stream()) since solid archives would otherwise be unpacked from the start for every page."""

    def __init__(self, path, sort="natural"):
        p = self.path = Path(path)
        ext = p.suffix.lower()
        self._lock = threading.Lock()
        self._zip = self._pdf = None
        self.closed = False
        self.kind = None
        self.names = []
        if p.is_dir():
            self.kind = "dir"
            self.names = pick_images((q.relative_to(p).as_posix() for q in p.rglob("*") if q.is_file()),
                                     sort_key(sort, file_mtime(p)))
        elif ext in (".zip", ".cbz") and zipfile.is_zipfile(p):
            self.kind = "zip"
            self._zip = zipfile.ZipFile(p)
            self.names = pick_images(self._zip.namelist(), sort_key(sort, zip_mtime(self._zip)))
        elif ext == ".pdf":
            import pypdfium2 as pdfium
            self.kind = "pdf"
            self._pdf = pdfium.PdfDocument(str(p))
            self.names = [f"{i + 1:04d}.png" for i in range(len(self._pdf))]
        elif ext in (".rar", ".cbr", ".7z", ".cb7"):
            self._exe = _seven_zip()
            if not self._exe:
                raise RuntimeError(tr("7-Zip behövs för rar/7z"))
            self.kind = "7z"
            self._entries = []  # (name with /, name in the archive, size) in archive order
            cur, mod = {}, {}
            r = subprocess.run([self._exe, "l", "-ba", "-slt", str(p)], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, creationflags=FLAGS, timeout=30)
            for ln in r.stdout.splitlines() + [""]:
                if not ln.strip():
                    if "Path" in cur and cur.get("Folder") != "+":
                        self._entries.append((cur["Path"].replace("\\", "/"), cur["Path"], int(cur.get("Size") or 0)))
                        mod[cur["Path"].replace("\\", "/")] = cur.get("Modified", "")
                    cur = {}
                elif " = " in ln:
                    k, v = ln.split(" = ", 1)
                    cur[k] = v
            orig = {e[0]: e[1] for e in self._entries}
            self.names = pick_images(orig, sort_key(sort, mod.__getitem__))
            self._orig = orig

    def read(self, i, pdf_scale=1.0):
        name = self.names[i]
        with self._lock:  # zip and pdfium do not handle concurrent reads; closed archive => error instead of a crash
            if self.closed:
                raise RuntimeError(tr("stängd"))
            if self.kind == "zip":
                return self._zip.read(name)
            if self.kind == "pdf":
                import cv2
                arr = self._pdf[i].render(scale=pdf_scale).to_numpy()
                ok, buf = cv2.imencode(".jpg", arr[:, :, :3] if arr.ndim == 3 else arr)
                return buf.tobytes()
        if self.kind == "dir":
            return (self.path / name).read_bytes()
        r = subprocess.run([self._exe, "e", "-so", str(self.path), self._orig[name]], capture_output=True,
                           stdin=subprocess.DEVNULL, creationflags=FLAGS, timeout=60)
        return r.stdout

    def stream(self):
        """(page index, bytes) for rar/7z with a single extraction to memory, in archive order."""
        idx = {n: i for i, n in enumerate(self.names)}
        proc = subprocess.Popen([self._exe, "e", "-so", str(self.path)], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=FLAGS)
        self._proc = proc
        try:
            for name, _orig, size in self._entries:
                data = proc.stdout.read(size) if size else b""
                if len(data) < size or self.closed:
                    return
                if name in idx:
                    yield idx[name], data
        finally:
            proc.kill()
            proc.wait()

    def close(self):
        with self._lock:
            self.closed = True
            if self._zip:
                self._zip.close()
            if self._pdf is not None:
                self._pdf.close()
        proc = getattr(self, "_proc", None)
        if proc:
            proc.kill()


def first_page(path):
    """(image bytes or None, page count or None) for a folder, an archive, a pdf or an image."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() in IMAGE_EXT:
        return p.read_bytes(), None
    try:
        src = PageSource(p)
    except RuntimeError:
        return None, None
    try:
        if not src.kind:
            return None, None
        return (src.read(0) if src.names else None), len(src.names)
    finally:
        src.close()


class _Sig(QObject):
    done = Signal(str, QImage, str)


class _Preview(QRunnable):
    def __init__(self, path, sig):
        super().__init__()
        self.path, self.sig = path, sig

    def run(self):
        info = ""
        img = QImage()
        try:
            data, n = first_page(self.path)
            if data:
                img = QImage.fromData(data)
                if max(img.width(), img.height()) > PREVIEW_MAX:
                    img = img.scaled(PREVIEW_MAX, PREVIEW_MAX, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
            if n is not None:
                info = tr("{n} sidor").format(n=n)
            elif data is None:
                info = tr("Ingen förhandsvisning (för rar/7z behövs 7-Zip)")
        except Exception as e:
            info = tr("Kunde inte läsa: {err}").format(err=e)
        try:
            self.sig.done.emit(self.path, img, info)
        except RuntimeError:
            pass


class _PreviewPane(QWidget):
    def __init__(self):
        super().__init__()
        self.pix = None
        self.img = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.img.setMinimumSize(120, 120)
        self.img.setStyleSheet("background:#1b1b1b;")
        self.info = QLabel(wordWrap=True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.img, 1)
        lay.addWidget(self.info)

    def show_image(self, img, info):
        self.pix = QPixmap.fromImage(img) if not img.isNull() else None
        self.info.setText(info)
        self._fit()

    def _fit(self):
        if self.pix:
            self.img.setPixmap(self.pix.scaled(self.img.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation))
        else:
            self.img.clear()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


class _PagesSig(QObject):
    done = Signal(int, int, QImage)  # generation, sidindex, miniatyr


def _thumb(data, size):
    """Decode directly at thumbnail size (jpeg is scaled in the decoder, much faster than full size)."""
    buf = QBuffer()
    buf.setData(QByteArray(data))
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    r = QImageReader(buf)
    sz = r.size()
    if sz.isValid():
        r.setScaledSize(sz.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio))
    return r.read()


class _PageThumbs(QRunnable):
    """Thumbnails for the pages in order; cancelled when another comic is selected (new generation)."""

    def __init__(self, grid, src, gen, pages):
        super().__init__()
        self.grid, self.src, self.gen, self.pages = grid, src, gen, pages

    def _emit(self, i, data):
        try:
            img = _thumb(data, self.size)
        except Exception:
            img = QImage()
        try:
            self.grid.sig.done.emit(self.gen, i, img)
        except RuntimeError:
            pass

    def run(self):
        self.size = self.grid.size
        try:
            if self.src.kind == "7z":
                for i, data in self.src.stream():
                    if self.grid.gen != self.gen:
                        return
                    self._emit(i, data)
                return
            for i in self.pages:
                if self.grid.gen != self.gen:
                    return
                self._emit(i, self.src.read(i, pdf_scale=0.4))
        except Exception:
            pass


class _PageGrid(QListWidget):
    """All pages of the selected comic as thumbnails, read from the archive in memory. Ctrl+wheel changes the size."""

    def __init__(self, state):
        super().__init__(viewMode=QListWidget.ViewMode.IconMode, resizeMode=QListWidget.ResizeMode.Adjust,
                         movement=QListWidget.Movement.Static, uniformItemSizes=True)
        self.state = state
        self.size = int(state.setting("browser_thumb", 150))
        self.setStyleSheet("QListWidget{background:#1b1b1b;}")
        self.gen = 0
        self.src = None
        self.done_n = 0
        self.bar = Progress(tr("Miniatyrer"))  # placed under the grid by the dialog
        self.sig = _PagesSig(self)
        self.sig.done.connect(self._done)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self._apply_size()

    def _apply_size(self):
        self.setIconSize(QSize(self.size, self.size))
        self.setGridSize(QSize(self.size + 14, self.size + 30))

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.size = max(80, min(420, self.size + (20 if e.angleDelta().y() > 0 else -20)))
            self.state.set_setting("browser_thumb", self.size)
            self._apply_size()
            if self.src:
                self.load(self.src)  # reload at the new size so the thumbnails are sharp
            return
        super().wheelEvent(e)

    def stop(self):
        self.gen += 1
        self.pool.clear()
        if self.src:
            self.src.close()
            self.src = None
        self.clear()
        self.bar.hide()

    def load(self, src):
        """Show src's pages. The grid owns src and closes it when something else is selected."""
        if src is not self.src:
            self.stop()
        self.gen += 1
        self.pool.clear()
        self.src = src
        self.clear()
        ph = QPixmap(self.size * 5 // 7, self.size)
        ph.fill(QColor(50, 50, 50))
        for i, n in enumerate(src.names):
            it = QListWidgetItem(QIcon(ph), str(i + 1))
            it.setToolTip(n)
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.addItem(it)
        n = len(src.names)
        self.done_n = 0
        self.bar.tick(0, n)
        if src.kind in ("7z", "pdf"):
            self.pool.start(_PageThumbs(self, src, self.gen, range(n)))  # one stream / one pdfium document at a time
        else:
            for k in range(3):
                self.pool.start(_PageThumbs(self, src, self.gen, range(k, n, 3)))

    def _done(self, gen, i, img):
        if gen != self.gen:
            return
        self.done_n += 1
        self.bar.tick(self.done_n, self.count())
        if not img.isNull() and i < self.count():
            self.item(i).setIcon(QIcon(QPixmap.fromImage(img)))

    def shutdown(self):
        self.stop()
        self.pool.waitForDone(3000)


class BrowserDialog(QDialog):
    """Pick a comic (folder, archive, pdf or image). The result is in .choice."""

    def __init__(self, parent, state, start_dir):
        super().__init__(parent)
        self.state = state
        self.choice = None
        self.setWindowTitle(tr("Öppna serie"))
        self.setAcceptDrops(True)
        self.resize(1300, 800)
        st = self.style()

        self.dirs = QFileSystemModel(self)
        self.dirs.setRootPath("")
        self.dirs.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Drives)
        self.tree = QTreeView()
        self.tree.setModel(self.dirs)
        for c in (1, 2, 3):
            self.tree.hideColumn(c)
        self.tree.setHeaderHidden(True)
        self.tree.clicked.connect(lambda ix: self.go(self.dirs.filePath(ix)))

        self.files = QFileSystemModel(self)
        self.files.setRootPath("")
        self.files.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot | QDir.Filter.Drives)
        self.files.setNameFilters([f"*{e}" for e in sorted(ARCHIVE_EXT | set(IMAGE_EXT))])
        self.files.setNameFilterDisables(False)
        self.list = QTreeView()
        self.list.setModel(self.files)
        self.list.setRootIsDecorated(False)
        self.list.setSortingEnabled(True)
        self.list.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.list.setUniformRowHeights(True)
        self.list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.list.setColumnWidth(0, 380)
        self.list.selectionModel().currentChanged.connect(lambda ix, _: self._select(self.files.filePath(ix)))
        self.list.doubleClicked.connect(lambda ix: self._activate(self.files.filePath(ix)))

        self.preview = _PreviewPane()
        self.grid = _PageGrid(state)
        self.grid.itemActivated.connect(lambda it: self._done(self.sel, it.data(Qt.ItemDataRole.UserRole)))
        self.stack = QStackedWidget()
        self.stack.addWidget(self.preview)
        self.stack.addWidget(self.grid)
        self.pages_btn = QPushButton(tr("Visa alla sidor (P)"), checkable=True)
        self.pages_btn.setToolTip(tr("Bläddra bland alla sidor i arkivet utan att packa upp det (Ctrl+hjul = storlek).")
                                  + "\n" + tr("Dubbelklicka på en sida för att öppna serien där."))
        self.pages_btn.setShortcut("P")
        self.pages_btn.setChecked(bool(state.setting("browser_pages", False)))
        self.pages_btn.toggled.connect(self._pages_mode)
        self.pages_info = QLabel()
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(self.pages_btn)
        row.addWidget(self.pages_info, 1)
        rl.addLayout(row)
        rl.addWidget(self.stack, 1)
        rl.addWidget(self.grid.bar)
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.addWidget(self.tree)
        self.split.addWidget(self.list)
        self.split.addWidget(right)
        self.split.setChildrenCollapsible(False)
        self.split.setStretchFactor(1, 2)
        self.split.setStretchFactor(2, 2)

        self.addr = QLineEdit()
        self.addr.returnPressed.connect(lambda: self.go(self.addr.text()))
        up = QPushButton(st.standardIcon(QStyle.StandardPixmap.SP_FileDialogToParent), "")
        up.setToolTip(tr("Upp en nivå"))
        up.clicked.connect(lambda: self.go(str(Path(self.cur).parent)))
        top = QHBoxLayout()
        top.addWidget(up)
        top.addWidget(self.addr, 1)

        self.open_dir = QPushButton(tr("Öppna mappen som serie"))
        self.open_dir.clicked.connect(lambda: self._done(self.sel or self.cur))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(lambda: self._activate(self.sel) if self.sel else None)
        bb.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel(tr("Dubbelklicka för att öppna, eller dra in filer hit.")))
        bottom.addStretch()
        bottom.addWidget(self.open_dir)
        bottom.addWidget(bb)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.split, 1)
        lay.addLayout(bottom)

        self.sig = _Sig(self)
        self.sig.done.connect(self._preview_done)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.sel = None
        self.cur = None
        self.page = None
        self.stack.setCurrentIndex(int(self.pages_btn.isChecked()))
        g = state.setting("browser_split")
        self.split.setSizes(g if g else [260, 600, 440])
        self.go(start_dir)

    def go(self, d):
        d = Path(d)
        if not d.is_dir():
            return
        self.cur = str(d)
        self.addr.setText(self.cur)
        ix = self.files.setRootPath(self.cur)
        self.list.setRootIndex(ix)
        self.tree.setCurrentIndex(self.dirs.index(self.cur))
        self.tree.scrollTo(self.dirs.index(self.cur))
        self.sel = None

    def _select(self, path):
        self.sel = path
        if self.pages_btn.isChecked():
            self._load_pages()
            return
        self.preview.show_image(QImage(), tr("Laddar förhandsvisning…"))
        self.pool.clear()
        self.pool.start(_Preview(path, self.sig))

    def _pages_mode(self, on):
        self.state.set_setting("browser_pages", on)
        self.stack.setCurrentIndex(int(on))
        if not on:
            self.grid.stop()
            self.pages_info.clear()
        if self.sel:
            self._select(self.sel)

    def _load_pages(self):
        self.grid.stop()
        p = Path(self.sel)
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            self.pages_info.setText(tr("Enskild bild"))
            return
        try:
            src = PageSource(p, self.state.setting("sort", "natural"))
        except Exception as e:
            self.pages_info.setText(tr("Kan inte visa sidorna: {err}").format(err=e))
            return
        if not src.names:
            src.close()
            self.pages_info.setText(tr("Inga bilder"))
            return
        self.pages_info.setText(tr("{n} sidor – dubbelklicka för att öppna där").format(n=len(src.names)))
        self.grid.load(src)

    def _preview_done(self, path, img, info):
        if path == self.sel:
            self.preview.show_image(img, f"{Path(path).name}\n{info}".strip())

    def _activate(self, path):
        if not path:
            return
        p = Path(path)
        if p.is_dir() and not any(q.suffix.lower() in IMAGE_EXT for q in p.iterdir() if q.is_file()):
            self.go(path)  # folder without images: enter it like Explorer does
        else:
            self._done(path)

    def _done(self, path, page=None):
        if path:
            self.choice, self.page = path, page
            self.accept()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            self._done(urls[0].toLocalFile())

    def done(self, r):
        self.state.set_setting("browser_split", self.split.sizes())
        self.grid.shutdown()
        self.pool.clear()
        self.pool.waitForDone(3000)
        super().done(r)
