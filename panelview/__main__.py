import sys

from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication


def _crash_log():
    """Skriv Python-stack vid hård krasch (segfault, minnesbrist i Qt) till <datamapp>/crash.log."""
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
    _log = _crash_log()  # noqa: F841 – filen måste hållas öppen
    app = QApplication(sys.argv)
    app.setApplicationName("AutoComix")
    app.setOrganizationName("AutoComix")
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    if (base / "assets" / "icon.png").exists():
        app.setWindowIcon(QIcon(str(base / "assets" / "icon.png")))
    from . import i18n, store
    import os
    i18n.setup(app, os.environ.get("AUTOCOMIX_LANG")  # för test: språk utan att ändra inställningen
               or store._read_json(store.STATE, {}).get("settings", {}).get("language", "auto"))
    from .mainwindow import MainWindow  # efter språket: listor på modulnivå översätts vid import
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    selftest = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--selftest=")), None)
    w = MainWindow(paths[0] if paths else None)
    # Öppnad med en serie (högerklick/dra på ikonen): direkt helskärm, annars senaste fönsterläge.
    w.show_initial(force_full=bool(paths) and "--window" not in sys.argv)
    if selftest:
        _selftest(app, w, selftest)
    sys.exit(app.exec())


def _selftest(app, w, out):
    """För byggkontroll (CI): vänta på första sidans rutor, skriv resultatet som JSON och avsluta."""
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
