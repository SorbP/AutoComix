# PyInstaller: bygger AutoComix som en körbar fil per plattform.
#   Windows: dist/AutoComix.exe   Linux: dist/AutoComix
# Kör:  pyinstaller AutoComix.spec   (på respektive plattform; korskompilering stöds inte av PyInstaller)
import sys

block_cipher = None
datas = [("models/panels_int8.onnx", "models"), ("assets/icon.png", "assets"),
         ("panelview/vendor/LICENSE_cbxy", "licenses"), ("LICENSES.md", ".")]
excl = ["tkinter", "matplotlib", "scipy", "pandas", "torch", "ultralytics", "PIL.ImageQt",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtSvg"]

a = Analysis(["AutoComix.pyw"], pathex=["."], datas=datas, hiddenimports=["py7zr", "pypdfium2"],
             excludes=excl, noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
icon = "assets/icon.ico" if sys.platform == "win32" else None

exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="AutoComix", console=False, icon=icon,
          upx=False, runtime_tmpdir=None)
