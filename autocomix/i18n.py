"""Language support: the interface texts are written in Swedish in the code and looked up in autocomix/lang/<code>.json.

tr("Öppna fil…") returns the translation (or the Swedish text if it is missing). Texts with values are written as
templates: tr("{n} sidor").format(n=5). The language is chosen in Settings ("auto" = the system language, otherwise
English) and is loaded by setup() before the rest of the interface is imported, so module-level lists are translated too.
"""
import json
import sys
from pathlib import Path

# (code, the language's own name); sv is the source language and has no file
LANGUAGES = (("en", "English"), ("sv", "Svenska"), ("de", "Deutsch"), ("fr", "Français"), ("es", "Español"),
             ("it", "Italiano"), ("pt_BR", "Português (Brasil)"), ("pl", "Polski"), ("ru", "Русский"),
             ("ja", "日本語"), ("zh_CN", "简体中文"), ("ko", "한국어"))

_T = {}
current = "sv"
qt_loaded = False  # Qt's own translation was found (the self-test reports it)


def lang_dir():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for p in (base / "autocomix" / "lang", Path(__file__).resolve().parent / "lang"):
        if p.is_dir():
            return p
    return Path(__file__).resolve().parent / "lang"


def resolve(setting):
    """'auto' -> the system language if available, otherwise English."""
    codes = [c for c, _ in LANGUAGES]
    if setting in codes:
        return setting
    from PySide6.QtCore import QLocale
    name = QLocale.system().name()  # t.ex. sv_SE, pt_BR, zh_CN
    for c in (name, name.split("_")[0]):
        if c in codes:
            return c
    return "en"


def load(code):
    global current
    current = code
    _T.clear()
    if code != "sv":
        try:
            _T.update(json.loads((lang_dir() / f"{code}.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass


def setup(app, setting):
    """Load the language and Qt's own texts (OK/Cancel, the color picker etc.)."""
    load(resolve(setting))
    from PySide6.QtCore import QLibraryInfo, QTranslator
    qt = QTranslator(app)
    global qt_loaded
    qt_loaded = qt.load(f"qtbase_{current}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    if qt_loaded:
        app.installTranslator(qt)


def tr(s):
    return _T.get(s) or s
