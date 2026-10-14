# PyInstaller: bygger PanelView som en körbar fil per plattform.
#   Windows: dist/PanelView.exe   Linux: dist/PanelView   macOS: dist/PanelView.app
# Kör:  pyinstaller PanelView.spec   (på respektive plattform; korskompilering stöds inte av PyInstaller)
import sys

block_cipher = None
datas = [("models/panels_int8.onnx", "models"), ("assets/icon.png", "assets"),
         ("panelview/vendor/LICENSE_cbxy", "licenses"), ("LICENSES.md", ".")]
excl = ["tkinter", "matplotlib", "scipy", "pandas", "torch", "ultralytics", "PIL.ImageQt",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
        "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtSvg"]

a = Analysis(["PanelView.pyw"], pathex=["."], datas=datas, hiddenimports=["py7zr", "pypdfium2"],
             excludes=excl, noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
icon = "assets/icon.ico" if sys.platform == "win32" else ("assets/icon.icns" if sys.platform == "darwin" else None)
if sys.platform == "darwin":
    import os
    icon = icon if os.path.exists(icon) else None

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PanelView", console=False, icon=icon)
    coll = COLLECT(exe, a.binaries, a.datas, name="PanelView")
    app = BUNDLE(coll, name="PanelView.app", icon=icon, bundle_identifier="se.panelview.reader",
                 info_plist={"CFBundleDocumentTypes": [{"CFBundleTypeName": "Comic", "CFBundleTypeRole": "Viewer",
                             "CFBundleTypeExtensions": ["cbz", "cbr", "cb7", "zip", "rar", "7z", "pdf"]}],
                             "NSHighResolutionCapable": True})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="PanelView", console=False, icon=icon,
              upx=False, runtime_tmpdir=None)
