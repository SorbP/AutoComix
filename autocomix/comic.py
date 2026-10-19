"""Open a comic: image folder, .cbz/.zip, .cbr/.rar, .cb7/.7z, .pdf."""
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path

from .i18n import tr

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")  # priority for duplicates
ARCHIVE_EXT = {".cbz", ".zip", ".cbr", ".rar", ".cb7", ".7z", ".pdf"}
PDF_SCALE = 2.0  # 144 dpi, sharp enough for full screen and panel zoom


class PasswordNeeded(Exception):
    """Encrypted archive: open again with a password."""


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def alpha_key(s):
    return s.lower()


SORTS = (("natural", tr("Naturlig (2 före 10)")), ("alpha", tr("Alfabetisk")), ("mtime", tr("Ändringsdatum (äldst först)")))


def sort_key(sort, mtime=None):
    """Sort key for page names. 'mtime': mtime(name) = date modified (random names), then natural."""
    if sort == "alpha":
        return alpha_key
    if sort != "mtime" or mtime is None:
        return natural_key

    def key(n):
        try:
            t = mtime(n)
        except (OSError, KeyError, ValueError, OverflowError):
            t = 0
        return (t, natural_key(n))
    return key


def file_mtime(root):
    return lambda n: (Path(root) / n).stat().st_mtime


def zip_mtime(zf):
    return lambda n: zf.getinfo(n).date_time


def pick_images(names, sort_key=natural_key):
    """Image names in natural order; the same name in several formats (x.png + x.webp) => keep the best."""
    best = {}
    for n in names:
        p = Path(n)
        ext = p.suffix.lower()
        if ext not in IMAGE_EXT or p.name.startswith(".") or "__MACOSX" in p.parts:
            continue
        key = p.with_suffix("").as_posix().lower()
        if key not in best or IMAGE_EXT.index(ext) < IMAGE_EXT.index(Path(best[key]).suffix.lower()):
            best[key] = n
    return sorted(best.values(), key=sort_key)


def _run(cmd, progress=None):
    """Run an extraction tool; 7-Zip's percent (-bsp1) is sent to progress. Returns (return code, end of output)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    tail = b""
    while True:
        chunk = p.stdout.read1(512)
        if not chunk:
            break
        tail = (tail + chunk)[-2000:]
        if progress:
            pct = re.findall(rb"(\d+)%", chunk)
            if pct:
                progress(int(pct[-1]))
    code = p.wait()
    if progress and code == 0:
        progress(100)  # small archives do not get to print anything above 0 %
    return code, tail.decode(errors="replace")


def _extract(archive, dest, password=None, progress=None):
    seven = next((e for e in ("7z", r"C:\Program Files\7-Zip\7z.exe") if shutil.which(e) or Path(e).exists()), None)
    if Path(archive).suffix.lower() in (".7z", ".cb7") and not seven:  # 7-Zip is faster and shows progress
        try:
            import py7zr
            with py7zr.SevenZipFile(archive, password=password) as z:
                if z.needs_password() and not password:
                    raise PasswordNeeded()
                z.extractall(dest)
            return
        except PasswordNeeded:
            raise
        except ImportError:
            pass
        except Exception as e:
            if "password" in str(e).lower():
                raise PasswordNeeded() from e
    tools = []
    for exe in ("7z", r"C:\Program Files\7-Zip\7z.exe"):
        if shutil.which(exe) or Path(exe).exists():
            tools.append([exe, "x", "-y", "-bsp1", f"-p{password or ''}", f"-o{dest}", str(archive)])
            break
    if shutil.which("unrar"):
        tools.append(["unrar", "x", "-o+", str(archive), str(dest) + "\\"])
    if shutil.which("tar"):
        tools.append(["tar", "-xf", str(archive), "-C", str(dest)])
    err = tr("inget verktyg (7z/unrar/tar) hittades")
    for cmd in tools:
        code, out = _run(cmd, progress)
        if code == 0:
            return
        err = out.strip()[-300:]
        if "password" in err.lower() or "encrypted" in err.lower():
            raise PasswordNeeded()
    raise RuntimeError(tr("Kunde inte packa upp {name}: {err}").format(name=Path(archive).name, err=err))


class Comic:
    def __init__(self, path, password=None, sort="natural", progress=None):
        self.path = Path(path)
        self._zip = self._tmp = self._pdf = None
        self._lock = threading.Lock()
        ext = self.path.suffix.lower()
        if self.path.is_dir():
            root = self.path
        elif ext == ".pdf":
            import pypdfium2 as pdfium
            try:
                self._pdf = pdfium.PdfDocument(str(self.path), password=password)
            except pdfium.PdfiumError as e:
                if "password" in str(e).lower():
                    raise PasswordNeeded() from e
                raise
            self.pages = [f"{i + 1:04d}.png" for i in range(len(self._pdf))]
            self._check()
            return
        elif ext in (".cbz", ".zip") and zipfile.is_zipfile(self.path):
            self._zip = zipfile.ZipFile(self.path)
            if password:
                self._zip.setpassword(password.encode())
            self.pages = pick_images(self._zip.namelist(), sort_key(sort, zip_mtime(self._zip)))
            self._check()
            if any(i.flag_bits & 1 for i in self._zip.infolist()) and not password:
                raise PasswordNeeded()
            return
        elif ext in ARCHIVE_EXT:
            self._tmp = tempfile.TemporaryDirectory(prefix="autocomix-")
            try:
                _extract(self.path, self._tmp.name, password, progress)
            except Exception:
                self._tmp.cleanup()
                raise
            root = Path(self._tmp.name)
        else:
            raise ValueError(tr("Okänt format: {name}").format(name=self.path.name))
        self.root = root
        self.pages = pick_images((p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()),
                                 sort_key(sort, file_mtime(root)))  # extracted rar/7z keep their dates
        self._check()

    def rtl_hint(self):
        """Reading direction from ComicInfo.xml (<Manga>YesAndRightToLeft</Manga>), otherwise None.

        The panel model only sees the shape of the panels, not whether the comic is manga, so the direction comes
        from metadata or is saved when R is pressed (then it applies to the whole folder)."""
        try:
            if self._zip:
                name = next((n for n in self._zip.namelist() if n.lower().endswith("comicinfo.xml")), None)
                data = self._zip.read(name) if name else None
            else:
                root = getattr(self, "root", None)
                f = next(root.rglob("[Cc]omic[Ii]nfo.xml"), None) if root else None
                data = f.read_bytes() if f else None
            if not data:
                return None
            import re as _re
            m = _re.search(rb"<Manga>\s*([^<]+?)\s*</Manga>", data, _re.I)
            if m:
                return m.group(1).lower() == b"yesandrighttoleft"
        except Exception:
            pass
        return None

    def _check(self):
        if not self.pages:
            raise FileNotFoundError(tr("Inga bilder i {path}").format(path=self.path))

    @property
    def title(self):
        return self.path.stem if self.path.is_file() else self.path.name

    def read(self, i):
        name = self.pages[i]
        if self._pdf is not None:
            import cv2
            with self._lock:  # pdfium is not thread-safe
                bmp = self._pdf[i].render(scale=PDF_SCALE)
                arr = bmp.to_numpy()
            ok, buf = cv2.imencode(".png", arr[:, :, :3] if arr.ndim == 3 else arr)
            return buf.tobytes()
        if self._zip:
            with self._lock:  # ZipFile does not handle concurrent reads from several threads
                return self._zip.read(name)
        return (self.root / name).read_bytes()

    def close(self):
        if self._pdf is not None:
            self._pdf.close()
        if self._zip:
            self._zip.close()
        if self._tmp:
            self._tmp.cleanup()

    def siblings(self):
        """Comics in the same parent folder (for next/previous comic)."""
        par = self.path.parent
        items = [p for p in par.iterdir()
                 if p.is_dir() or p.suffix.lower() in ARCHIVE_EXT]
        return sorted(items, key=lambda p: natural_key(p.name))
