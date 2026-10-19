import sys

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication


def _crash_log():
    """Write the Python stack on a hard crash (segfault, out of memory in Qt) to <data folder>/crash.log."""
    import faulthandler
    from . import store
    try:
        store.BASE.mkdir(parents=True, exist_ok=True)
        log = store.BASE / "crash.log"
        if log.exists() and log.stat().st_size > 1_000_000:
            log.unlink()
        f = open(log, "a", encoding="utf-8")
        faulthandler.enable(f)
        return f
    except OSError:
        return None


def main():
    _log = _crash_log()  # noqa: F841 – the file must stay open
    app = QApplication(sys.argv)
    app.setApplicationName("AutoComix")
    app.setOrganizationName("AutoComix")
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    if (base / "assets" / "icon.png").exists():
        app.setWindowIcon(QIcon(str(base / "assets" / "icon.png")))
    from . import i18n, store
    import os
    settings = store._read_json(store.STATE, {}).get("settings")
    # Installs from before 2.19 were Swedish-only: keep Swedish there; new installs follow the system language.
    lang = settings.get("language", "sv") if settings else "auto"
    if settings and "language" not in settings:  # save it so Settings shows Svenska, not Automatic
        data = store._read_json(store.STATE, {})
        data["settings"]["language"] = "sv"
        store._write_json(store.STATE, data)
    i18n.setup(app, os.environ.get("AUTOCOMIX_LANG") or lang)  # AUTOCOMIX_LANG: test a language without the setting
    from .mainwindow import MainWindow  # after the language: module-level lists are translated on import
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    selftest = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--selftest=")), None)
    w = MainWindow(paths[0] if paths else None)
    # Opened with a comic (right-click/drop on the icon): straight to full screen, otherwise the last window mode.
    w.show_initial(force_full=bool(paths) and "--window" not in sys.argv)
    if selftest:
        _selftest(app, w, selftest)
    sys.exit(app.exec())


def _selftest(app, w, out):
    """For build checks (CI): wait for the first page's panels, write the result as JSON and exit."""
    import json
    import time

    from . import i18n

    from PySide6.QtCore import QTimer
    t0 = time.time()

    def poll():
        v = w.v
        ps, ready = v.panels() if v.comic and v.spreads else ([], False)
        if ready or time.time() - t0 > 90:
            res = {"ok": bool(ready), "pages": len(v.comic.pages) if v.comic else 0, "panels": len(ps),
                   "ml": bool(v.detector and v.detector.ml_ok), "seconds": round(time.time() - t0, 1),
                   "lang": i18n.current, "lang_files": len(list(i18n.lang_dir().glob("*.json"))),
                   "qt_translation": i18n.qt_loaded}
            Path(out).write_text(json.dumps(res), encoding="utf-8")
            w.close()
            app.quit()
        else:
            QTimer.singleShot(200, poll)
    QTimer.singleShot(200, poll)


if __name__ == "__main__":
    main()
