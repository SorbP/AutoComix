"""Samlar licenstexterna för allt som byggs in i AutoComix (körs av AutoComix.spec, går också att köra direkt).

  python build_tools/collect_licenses.py <utmapp>

Utmappen får: LICENSE (AutoComix, AGPL-3.0), LICENSES.md, standardtexterna i licenses/, en mapp per inbyggt
Python-paket med paketets egna licensfiler (ur dist-info), Pythons licens och KÄLLKOD.txt (var källkoden finns
och hur LGPL-biblioteken byts ut). Paketen hittas från requirements.txt och deras beroenden, så listan följer med
när beroendena ändras.
"""
import importlib.metadata as md
import re
import shutil
import sys
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
LIC_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS|ThirdParty)", re.I)
# Paket utan egna licensfiler i dist-info, eller där filen inte är den licens vi använder.
NOTES = {
    "flatbuffers": "Apache-2.0 (se ../apache-2.0.txt). Källa: https://github.com/google/flatbuffers",
    "pyside6-essentials": ("Används under LGPL-3.0 (se ../lgpl-3.0.txt och ../gpl-3.0.txt). Omodifierad.\n"
                           "Källkod: https://code.qt.io/cgit/pyside/pyside-setup.git (PySide6) och "
                           "https://download.qt.io/official_releases/qt/ (Qt).\n"
                           "Tredjepartskomponenter i Qt: https://doc.qt.io/qt-6/licenses-used-in-qt.html"),
    "shiboken6": ("Används under LGPL-3.0 (se ../lgpl-3.0.txt och ../gpl-3.0.txt). Omodifierad.\n"
                  "Källkod: https://code.qt.io/cgit/pyside/pyside-setup.git"),
}
SKIP_FILES = {"LicenseRef-Qt-Commercial.txt"}  # PySide6 används inte under den kommersiella licensen

KALLKOD = """AutoComix är fri programvara under GNU Affero General Public License v3.0 (se LICENSE).
Källkod: https://github.com/SorbP/PanelView

Inbyggda bibliotek under LGPL (Qt/PySide6/shiboken6: LGPL-3.0; py7zr, pybcj, pyppmd, inflate64,
multivolumefile: LGPL-2.1 eller senare) är omodifierade. Deras källkod finns hos respektive projekt
(länkar i licenses/<paket>/). Programmet är byggt i mappläge, så biblioteken ligger som separata filer
under _internal/ och kan bytas mot andra kompatibla versioner. Vill du bygga om allt: klona källkoden
och kör pyinstaller AutoComix.spec (se README.md).

Rutmodellen models/panels_int8.onnx kommer från mosesb/best-comic-panel-detection (märkt Apache-2.0),
som är tränad med Ultralytics/YOLOv12 (AGPL-3.0). Den sprids här under AGPL-3.0 tillsammans med programmet.
"""


def packages():
    """Alla installerade distributioner som requirements.txt drar in (rekursivt, utan extras)."""
    roots = [Requirement(l).name for l in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    seen, out, stack = set(), [], roots
    while stack:
        name = stack.pop()
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        try:
            d = md.distribution(name)
        except md.PackageNotFoundError:
            continue
        out.append(d)
        for r in d.requires or []:
            req = Requirement(r)
            if not req.marker or req.marker.evaluate({"extra": ""}):
                stack.append(req.name)
    return sorted(out, key=lambda d: d.metadata["Name"].lower())


def collect(dst):
    dst = Path(dst)
    lic = dst / "licenses"
    if lic.exists():
        shutil.rmtree(lic)
    shutil.copytree(ROOT / "licenses", lic)
    shutil.copy(ROOT / "LICENSE", dst / "LICENSE")
    shutil.copy(ROOT / "LICENSES.md", dst / "LICENSES.md")
    (dst / "KÄLLKOD.txt").write_text(KALLKOD, encoding="utf-8")
    shutil.copy(ROOT / "panelview" / "vendor" / "LICENSE_cbxy", lic / "cbxy-LICENSE.txt")
    py = Path(sys.base_prefix) / "LICENSE.txt"
    if py.exists():
        shutil.copy(py, lic / f"python-{sys.version.split()[0]}-LICENSE.txt")
    rows = []
    for d in packages():
        name, ver = d.metadata["Name"], d.version
        key = name.lower().replace("_", "-")
        pd = lic / f"{key}-{ver}"
        pd.mkdir(exist_ok=True)
        n = 0
        for f in d.files or []:
            if LIC_FILE.search(str(f)) and not str(f).endswith((".py", ".pyc")) and f.name not in SKIP_FILES:
                src = Path(d.locate_file(f))
                if src.is_file():
                    shutil.copy(src, pd / "_".join(f.parts[1:] if len(f.parts) > 1 else f.parts))
                    n += 1
        if key in NOTES:
            (pd / "LICENS.txt").write_text(NOTES[key] + "\n", encoding="utf-8")
            n += 1
        expr = d.metadata.get("License-Expression") or d.metadata.get("License") or ""
        rows.append(f"{name} {ver}: {expr if len(expr) < 80 else '(se filerna)'}")
        if not n:
            print(f"VARNING: inga licensfiler för {name}", file=sys.stderr)
    (lic / "PAKET.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "build" / "licenses_out")
    out.mkdir(parents=True, exist_ok=True)
    print("\n".join(collect(out)))
