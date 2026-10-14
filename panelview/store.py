"""Lokal lagring: rutcache per serie, läsläge/sida per serie, inställningar."""
import hashlib
import json
import os
import zipfile
from pathlib import Path

import sys


def _base():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PanelView"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PanelView"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "PanelView"


BASE = _base()
CACHE = BASE / "cache"
STATE = BASE / "state.json"


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
    """Samma placering som cbxy: mapp/<mappnamn>.cbxy eller bok.cbxy bredvid arkivet."""
    path = Path(path)
    return path / f"{path.name}.cbxy" if path.is_dir() else path.with_suffix(".cbxy")


def load_sidecar(path):
    """{sidnamn: [rutor]} från en .cbxy, eller {} (t.ex. rättad i cbxy-editor)."""
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
    """Rå CV- och ML-rutor per sida, sparas som en JSON-fil per serie."""

    def __init__(self, path):
        h = hashlib.sha1(comic_key(path).encode()).hexdigest()[:16]
        self.file = CACHE / f"{h}.json"
        self.data = _read_json(self.file, {"v": 1, "pages": {}})
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

    def rtl(self, path):
        c = self.comic(path)
        if "rtl" in c:
            return c["rtl"]
        return self.d["dirs"].get(comic_key(Path(path).parent), {}).get("rtl", False)

    def set_rtl(self, path, rtl):
        # Sparas även på föräldramappen så att andra delar i samma serie ärver valet.
        self.d["comics"].setdefault(comic_key(path), {})["rtl"] = rtl
        self.d["dirs"].setdefault(comic_key(Path(path).parent), {})["rtl"] = rtl
        self.save()

    def set_page(self, path, page):
        self.d["comics"].setdefault(comic_key(path), {})["page"] = page
        self.d["last"] = str(path)

    # ---------- historik ----------
    def add_history(self, path, limit=20):
        h = [x for x in self.d.setdefault("history", []) if comic_key(x) != comic_key(path)]
        self.d["history"] = [str(path)] + h[:limit - 1]
        self.save()

    def history(self):
        return [h for h in self.d.get("history", []) if Path(h).exists()]

    def clear_history(self):
        self.d["history"] = []
        self.save()

    # ---------- bokmärken ----------
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
