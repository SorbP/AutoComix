"""Local storage: panel cache per comic, reading mode/page per comic, settings."""
import hashlib
import json
import os
import zipfile
from pathlib import Path

import sys


def _base():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AutoComix"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "AutoComix"


def _migrate(base):
    """The program was called PanelView before 2.16: move the old data folder (settings, cache, models) once."""
    old = base.with_name("PanelView")
    if old.is_dir() and not base.exists():
        try:
            old.rename(base)
        except OSError:  # e.g. a file open in an old instance: copy instead, the old folder stays
            import shutil
            shutil.copytree(old, base)
    return base


BASE = _migrate(_base())
CACHE = BASE / "cache"
STATE = BASE / "state.json"
CACHE_VERSION = 2  # raised when the panel detection changes


def _read_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def comic_key(path):
    return str(Path(path).resolve()).lower()


def sidecar_path(path):
    """Same location as cbxy: folder/<folder name>.cbxy or book.cbxy next to the archive."""
    path = Path(path)
    return path / f"{path.name}.cbxy" if path.is_dir() else path.with_suffix(".cbxy")


def load_sidecar(path):
    """{page name: [panels]} from a .cbxy, or {} (e.g. corrected in cbxy-editor)."""
    sc = sidecar_path(path)
    if not sc.exists():
        return {}
    out = {}
    try:
        with zipfile.ZipFile(sc) as z:
            for n in z.namelist():
                try:
                    d = json.loads(z.read(n))
                except ValueError:
                    continue
                page = d.get("page") or n
                out[Path(page).stem.lower()] = d.get("panels", [])
    except (OSError, zipfile.BadZipFile):
        return {}
    return out


class PanelCache:
    """Raw CV and ML panels per page, saved as one JSON file per comic."""

    def __init__(self, path):
        h = hashlib.sha1(comic_key(path).encode()).hexdigest()[:16]
        self.file = CACHE / f"{h}.json"
        from .ml_onnx import model_id
        mid = model_id()
        self.data = _read_json(self.file, {"v": CACHE_VERSION, "model": mid, "pages": {}})
        if self.data.get("v") != CACHE_VERSION or self.data.get("model") != mid:  # new method/model: redo the pages
            self.data = {"v": CACHE_VERSION, "model": mid, "pages": {}}
        self.dirty = 0

    def get(self, name):
        return self.data["pages"].get(name)

    def put(self, name, cv, ml):
        self.data["pages"][name] = {"cv": cv, "ml": ml}
        self.dirty += 1
        if self.dirty >= 5:
            self.save()

    def save(self):
        if self.dirty:
            _write_json(self.file, self.data)
            self.dirty = 0


class UserPanels:
    """Panels the user drew/corrected in edit mode, per comic. Take precedence over the automatic detection
    and are never reset when the detection changes."""

    def __init__(self, path):
        h = hashlib.sha1(comic_key(path).encode()).hexdigest()[:16]
        self.file = BASE / "edits" / f"{h}.json"
        self.data = _read_json(self.file, {"path": str(path), "pages": {}})

    def get(self, name):
        return self.data["pages"].get(name)

    def set(self, name, boxes):
        if boxes is None:
            self.data["pages"].pop(name, None)
        else:
            self.data["pages"][name] = boxes
        _write_json(self.file, self.data)


def training_counts():
    """(corrected, approved) pages in the training data."""
    idx = _read_json(BASE / "training" / "index.json", {})
    return sum(v == "rättad" for v in idx.values()), sum(v == "godkänd" for v in idx.values())


def save_training_example(jpg_bytes, boxes, key, kind="rättad"):
    """Page + panels in YOLO format under BASE/training (images/ + labels/), for retraining the model."""
    d = BASE / "training"
    (d / "images").mkdir(parents=True, exist_ok=True)
    (d / "labels").mkdir(parents=True, exist_ok=True)
    (d / "images" / f"{key}.jpg").write_bytes(jpg_bytes)
    lines = [f"0 {b['x'] + b['w'] / 2:.6f} {b['y'] + b['h'] / 2:.6f} {b['w']:.6f} {b['h']:.6f}" for b in boxes]
    idx = _read_json(d / "index.json", {})
    idx[key] = "rättad" if kind == "rättad" or idx.get(key) == "rättad" else "godkänd"
    _write_json(d / "index.json", idx)
    (d / "labels" / f"{key}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


class State:
    def __init__(self):
        self.d = _read_json(STATE, {})
        self.d.setdefault("comics", {})
        self.d.setdefault("dirs", {})
        self.d.setdefault("settings", {"dim": True, "overview": False, "guided": True})

    def setting(self, k, default=None):
        return self.d["settings"].get(k, default)

    def set_setting(self, k, v):
        self.d["settings"][k] = v
        self.save()

    def comic(self, path):
        return self.d["comics"].get(comic_key(path), {})

    def rtl(self, path, hint=None):
        """Saved choice for the comic, otherwise the folder's, otherwise metadata (ComicInfo.xml), otherwise left→right."""
        c = self.comic(path)
        if "rtl" in c:
            return c["rtl"]
        d = self.d["dirs"].get(comic_key(Path(path).parent), {})
        if "rtl" in d:
            return d["rtl"]
        return bool(hint)

    def set_rtl(self, path, rtl):
        # Also saved on the parent folder so other parts of the same series inherit the choice.
        self.d["comics"].setdefault(comic_key(path), {})["rtl"] = rtl
        self.d["dirs"].setdefault(comic_key(Path(path).parent), {})["rtl"] = rtl
        self.save()

    def set_page(self, path, page, panel=None):
        c = self.d["comics"].setdefault(comic_key(path), {})
        c["page"] = page
        if panel is None:
            c.pop("panel", None)  # new page without a known panel: start from the first
        else:
            c["panel"] = panel
        self.d["last"] = str(path)

    # ---------- historik ----------
    def add_history(self, path, pages=None, limit=20):
        import time
        h = [x for x in self.d.setdefault("history", []) if comic_key(x) != comic_key(path)]
        self.d["history"] = [str(path)] + h[:limit - 1]
        c = self.d["comics"].setdefault(comic_key(path), {})
        c["opened"] = int(time.time())
        if pages:
            c["pages"] = pages
        self.save()

    def history(self):
        return [h for h in self.d.get("history", []) if Path(h).exists()]

    def clear_history(self):
        self.d["history"] = []
        self.save()

    # ---------- bookmarks ----------
    def bookmarks(self):
        return self.d.setdefault("bookmarks", [])

    def add_bookmark(self, path, page, name):
        import time
        self.bookmarks().append({"path": str(path), "page": page, "name": name, "time": int(time.time())})
        self.save()

    def remove_bookmark(self, i):
        del self.bookmarks()[i]
        self.save()

    # ---------- tangenter ----------
    def keys(self):
        return self.d.setdefault("keys", {})

    def set_keys(self, k, seqs):
        self.keys()[k] = seqs
        self.save()

    def save(self):
        _write_json(STATE, self.d)
