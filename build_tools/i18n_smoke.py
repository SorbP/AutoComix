"""Röktest: gränssnittet byggs på varje språk i panelview/lang (menyer, inställningar, hjälp, statusrader).
Kör:  .venv/Scripts/python build_tools/i18n_smoke.py [kod ...]
"""
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def one(code):
    import tempfile
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from panelview import i18n, store
    tmp = Path(tempfile.mkdtemp(prefix="pv_i18n_"))
    store.BASE, store.CACHE, store.STATE = tmp, tmp / "cache", tmp / "state.json"
    i18n.setup(app, code)
    from panelview.mainwindow import MainWindow, OptionsDialog
    w = MainWindow()
    w.show()
    menus = [m.title() for m in w.menus]
    OptionsDialog(w).close()
    w.help_text()
    from PySide6.QtGui import QColor, QImage
    pages = tmp / "serie"
    pages.mkdir()
    for k in range(3):
        img = QImage(400, 600, QImage.Format.Format_RGB32)
        img.fill(QColor(240, 240, 240))
        img.save(str(pages / f"{k}.png"))
    w.v.open(str(pages))
    w.v.status_parts()
    for fn in (w.v.toggle_edit, w.v.toggle_edit, w.v.toggle_order, w.v.toggle_order, w.cycle_second, w.cycle_second):
        fn()
        w.v.grab()  # ritar informationsrader och hjälptexter
    w.v.show_help = True
    w.v.grab()
    w.close()
    print(i18n.current, " | ".join(menus))
    return i18n.current == code and menus[0] != "&Arkiv" if code != "sv" else menus[0] == "&Arkiv"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-") and "," not in sys.argv[1] and sys.argv[1] != "all":
        sys.exit(0 if one(sys.argv[1]) else 1)
    codes = sys.argv[1:] or ["sv"] + sorted(p.stem for p in (ROOT / "panelview" / "lang").glob("*.json"))
    bad = 0
    for c in codes:  # en process per språk: listor på modulnivå översätts vid import
        r = subprocess.run([sys.executable, __file__, c], capture_output=True, text=True, encoding="utf-8",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        ok = r.returncode == 0
        bad += not ok
        print(f"{'OK  ' if ok else 'FEL '} {r.stdout.strip() or r.stderr.strip()[-600:]}")
    print(f"\n{len(codes) - bad}/{len(codes)} OK")
    sys.exit(1 if bad else 0)
