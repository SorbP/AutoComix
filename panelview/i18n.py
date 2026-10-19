"""Språkstöd: gränssnittets texter skrivs på svenska i koden och slås upp i panelview/lang/<kod>.json.

tr("Öppna fil…") ger översättningen (eller den svenska texten om den saknas). Texter med värden skrivs som
mallar: tr("{n} sidor").format(n=5). Språket väljs i Inställningar ("auto" = systemets språk, annars engelska)
och läses in av setup() innan resten av gränssnittet importeras, så att listor på modulnivå också översätts.
"""
import json
import sys
from pathlib import Path

# (kod, namn på språket självt); sv är källspråket och har ingen fil
LANGUAGES = (("en", "English"), ("sv", "Svenska"), ("de", "Deutsch"), ("fr", "Français"), ("es", "Español"),
             ("it", "Italiano"), ("pt_BR", "Português (Brasil)"), ("pl", "Polski"), ("ru", "Русский"),
             ("ja", "日本語"), ("zh_CN", "简体中文"), ("ko", "한국어"))

_T = {}
current = "sv"
qt_loaded = False  # Qt:s egna översättning hittades (självtestet rapporterar det)


def lang_dir():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for p in (base / "panelview" / "lang", Path(__file__).resolve().parent / "lang"):
        if p.is_dir():
            return p
    return Path(__file__).resolve().parent / "lang"


def resolve(setting):
    """'auto' -> systemets språk om det finns, annars engelska."""
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
    """Läs in språket och Qt:s egna texter (OK/Avbryt, färgväljaren m.m.)."""
    load(resolve(setting))
    from PySide6.QtCore import QLibraryInfo, QTranslator
    qt = QTranslator(app)
    global qt_loaded
    qt_loaded = qt.load(f"qtbase_{current}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    if qt_loaded:
        app.installTranslator(qt)


def tr(s):
    return _T.get(s) or s
