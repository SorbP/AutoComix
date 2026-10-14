"""Filbläddrare med förhandsvisning (L): mappträd | fillista | förhandsvisning, med dragbara avdelare.

Fillistan använder systemets ikoner och kolumner (namn, storlek, typ, ändrad) som Utforskaren. Förhandsvisningen visar
första sidan ur mappar, zip/cbz, pdf och (med 7-Zip) rar/7z, samt antal sidor.
"""
import shutil
import subprocess
import zipfile
from pathlib import Path

from PySide6.QtCore import QDir, QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileSystemModel, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QSplitter, QStyle, QTreeView, QVBoxLayout, QWidget)

from .comic import ARCHIVE_EXT, IMAGE_EXT, natural_key, pick_images

PREVIEW_MAX = 1600


def _seven_zip():
    for exe in ("7z", r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if shutil.which(exe) or Path(exe).exists():
            return exe
    return None


def first_page(path):
    """(bildbytes eller None, antal sidor eller None) för en mapp, ett arkiv, en pdf eller en bild."""
    p = Path(path)
    ext = p.suffix.lower()
    if p.is_dir():
        imgs = pick_images(q.relative_to(p).as_posix() for q in p.rglob("*") if q.is_file())
        return ((p / imgs[0]).read_bytes() if imgs else None), len(imgs)
    if ext in IMAGE_EXT:
        return p.read_bytes(), None
    if ext in (".zip", ".cbz") and zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:
            imgs = pick_images(z.namelist())
            return (z.read(imgs[0]) if imgs else None), len(imgs)
    if ext == ".pdf":
        import cv2
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(p))
        try:
            arr = doc[0].render(scale=1.0).to_numpy()
            ok, buf = cv2.imencode(".png", arr[:, :, :3] if arr.ndim == 3 else arr)
            return buf.tobytes(), len(doc)
        finally:
            doc.close()
    if ext in (".rar", ".cbr", ".7z", ".cb7"):
        exe = _seven_zip()
        if not exe:
            return None, None
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run([exe, "l", "-ba", "-slt", str(p)], capture_output=True, text=True, creationflags=flags,
                           timeout=30)
        names = [ln[7:] for ln in r.stdout.splitlines() if ln.startswith("Path = ")]
        imgs = pick_images(names)
        if not imgs:
            return None, 0
        r = subprocess.run([exe, "e", "-so", str(p), imgs[0]], capture_output=True, creationflags=flags, timeout=60)
        return (r.stdout or None), len(imgs)
    return None, None


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
                info = f"{n} sidor"
            elif data is None:
                info = "Ingen förhandsvisning (för rar/7z behövs 7-Zip)"
        except Exception as e:
            info = f"Kunde inte läsa: {e}"
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


class BrowserDialog(QDialog):
    """Välj en serie (mapp, arkiv, pdf eller bild). Resultatet ligger i .choice."""

    def __init__(self, parent, state, start_dir):
        super().__init__(parent)
        self.state = state
        self.choice = None
        self.setWindowTitle("Öppna serie")
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
        self.split = QSplitter(Qt.Orientation.Horizontal)
        self.split.addWidget(self.tree)
        self.split.addWidget(self.list)
        self.split.addWidget(self.preview)
        self.split.setChildrenCollapsible(False)
        self.split.setStretchFactor(1, 2)
        self.split.setStretchFactor(2, 2)

        self.addr = QLineEdit()
        self.addr.returnPressed.connect(lambda: self.go(self.addr.text()))
        up = QPushButton(st.standardIcon(QStyle.StandardPixmap.SP_FileDialogToParent), "")
        up.setToolTip("Upp en nivå")
        up.clicked.connect(lambda: self.go(str(Path(self.cur).parent)))
        top = QHBoxLayout()
        top.addWidget(up)
        top.addWidget(self.addr, 1)

        self.open_dir = QPushButton("Öppna mappen som serie")
        self.open_dir.clicked.connect(lambda: self._done(self.sel or self.cur))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(lambda: self._activate(self.sel) if self.sel else None)
        bb.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Dubbelklicka för att öppna, eller dra in filer hit."))
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
        self.preview.show_image(QImage(), "Laddar förhandsvisning…")
        self.pool.clear()
        self.pool.start(_Preview(path, self.sig))

    def _preview_done(self, path, img, info):
        if path == self.sel:
            self.preview.show_image(img, f"{Path(path).name}\n{info}".strip())

    def _activate(self, path):
        if not path:
            return
        p = Path(path)
        if p.is_dir() and not any(q.suffix.lower() in IMAGE_EXT for q in p.iterdir() if q.is_file()):
            self.go(path)  # mapp utan bilder: gå in i den som i Utforskaren
        else:
            self._done(path)

    def _done(self, path):
        if path:
            self.choice = path
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
        self.pool.clear()
        self.pool.waitForDone(3000)
        super().done(r)
