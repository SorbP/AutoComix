"""Öppna en serie: bildmapp, .cbz/.zip, .cbr/.rar, .cb7/.7z, .pdf."""
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff")  # prioritet vid dubbletter
ARCHIVE_EXT = {".cbz", ".zip", ".cbr", ".rar", ".cb7", ".7z", ".pdf"}
PDF_SCALE = 2.0  # 144 dpi, skarpt nog för helskärm och rutzoom


class PasswordNeeded(Exception):
    """Krypterat arkiv: öppna igen med lösenord."""


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def alpha_key(s):
    return s.lower()


SORTS = (("natural", "Naturlig (2 före 10)"), ("alpha", "Alfabetisk"), ("mtime", "Ändringsdatum (äldst först)"))


def sort_key(sort, mtime=None):
    """Sorteringsnyckel för sidnamn. 'mtime': mtime(namn) = ändringsdatum (slumpmässiga namn), sedan naturlig."""
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
    """Bildnamn i naturlig ordning; samma namn i flera format (x.png + x.webp) => behåll bästa."""
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
    """Kör ett uppackningsverktyg; 7-Zips procent (-bsp1) skickas till progress. Ger (returkod, utskriftens slut)."""
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
        progress(100)  # små arkiv hinner inte skriva ut något över 0 %
    return code, tail.decode(errors="replace")


def _extract(archive, dest, password=None, progress=None):
    seven = next((e for e in ("7z", r"C:\Program Files\7-Zip\7z.exe") if shutil.which(e) or Path(e).exists()), None)
    if Path(archive).suffix.lower() in (".7z", ".cb7") and not seven:  # 7-Zip är snabbare och visar förlopp
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
    err = "inget verktyg (7z/unrar/tar) hittades"
    for cmd in tools:
        code, out = _run(cmd, progress)
        if code == 0:
            return
        err = out.strip()[-300:]
        if "password" in err.lower() or "encrypted" in err.lower():
            raise PasswordNeeded()
    raise RuntimeError(f"Kunde inte packa upp {Path(archive).name}: {err}")


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
            self._tmp = tempfile.TemporaryDirectory(prefix="panelview-")
            try:
                _extract(self.path, self._tmp.name, password, progress)
            except Exception:
                self._tmp.cleanup()
                raise
            root = Path(self._tmp.name)
        else:
            raise ValueError(f"Okänt format: {self.path.name}")
        self.root = root
        self.pages = pick_images((p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()),
                                 sort_key(sort, file_mtime(root)))  # uppackade rar/7z behåller datumen
        self._check()

    def rtl_hint(self):
        """Läsriktning ur ComicInfo.xml (<Manga>YesAndRightToLeft</Manga>), annars None.

        Rutmodellen ser bara rutornas form, inte om serien är manga, så riktningen tas ur metadata
        eller sparas när man trycker R (gäller sedan hela mappen)."""
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
            raise FileNotFoundError(f"Inga bilder i {self.path}")

    @property
    def title(self):
        return self.path.stem if self.path.is_file() else self.path.name

    def read(self, i):
        name = self.pages[i]
        if self._pdf is not None:
            import cv2
            with self._lock:  # pdfium är inte trådsäkert
                bmp = self._pdf[i].render(scale=PDF_SCALE)
                arr = bmp.to_numpy()
            ok, buf = cv2.imencode(".png", arr[:, :, :3] if arr.ndim == 3 else arr)
            return buf.tobytes()
        if self._zip:
            with self._lock:  # ZipFile tål inte samtidiga läsningar från flera trådar
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
        """Serier i samma föräldramapp (för nästa/föregående serie)."""
        par = self.path.parent
        items = [p for p in par.iterdir()
                 if p.is_dir() or p.suffix.lower() in ARCHIVE_EXT]
        return sorted(items, key=lambda p: natural_key(p.name))
