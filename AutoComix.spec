# PyInstaller: builds AutoComix in folder mode per platform (the Qt/LGPL libraries are separate, replaceable files).
#   Windows: dist/AutoComix/AutoComix.exe   Linux: dist/AutoComix/AutoComix
# The license texts (LICENSE, LICENSES.md/LICENSES.sv.md, licenses/, SOURCE.txt, KÄLLKOD.txt) go at the top of the program folder.
# Run:  pyinstaller AutoComix.spec   (on each platform; PyInstaller does not support cross-compiling)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH) / "build_tools"))
import collect_licenses  # noqa: E402

block_cipher = None
datas = [("models/panels_int8.onnx", "models"), ("assets/icon.png", "assets"), ("autocomix/lang", "autocomix/lang")]
excl = ["tkinter", "matplotlib", "scipy", "pandas", "torch", "ultralytics", "PIL.ImageQt",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtSvg"]

a = Analysis(["AutoComix.pyw"], pathex=["."], datas=datas, hiddenimports=["py7zr", "pypdfium2"],
             excludes=excl, noarchive=False,
             module_collection_mode={"py7zr": "py", "multivolumefile": "py"})  # LGPL: as replaceable .py files
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
icon = "assets/icon.ico" if sys.platform == "win32" else None

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="AutoComix", console=False, icon=icon, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="AutoComix", upx=False)
collect_licenses.collect(Path(DISTPATH) / "AutoComix")
