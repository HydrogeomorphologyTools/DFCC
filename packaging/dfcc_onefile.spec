# PyInstaller spec:  pyinstaller packaging/dfcc_onefile.spec   (run from the packaging folder)
# Builds a single self-contained DFCC.exe (one-file mode): no _internal folder next to it.
# At each start the bundle is unpacked to a temporary folder (%TEMP%\_MEIxxxx), so start-up is slower than the one-folder build.
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hidden = [], [], collect_submodules("dfcc")
for pkg in ("numba", "llvmlite", "rasterio", "shapefile"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception as e:           # optional pieces (e.g. PySide6 absent) are tolerated
        print("collect_all skipped", pkg, e)
datas += [("dfcc.ico", "."), ("../src/dfcc/gui/help", "dfcc/gui/help"), ("../docs/logo.png", "docs"), ("../docs/METHOD.md", "docs"), ("../README.md", "."),
          ("../qgis_plugin", "qgis_plugin"), ("../arcgis_toolbox", "arcgis_toolbox")]
hidden += ["rasterio.sample", "rasterio.vrt", "rasterio._features", "rasterio.rpc", "rasterio.crs"]

a = Analysis(["dfcc_entry.py"], pathex=["../src"], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "IPython", "pytest", "scipy", "pandas", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtDesigner", "PySide6.QtSql", "PySide6.QtBluetooth", "PySide6.QtNetwork"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="DFCC",
          console=True,                 # console build: CLI output works; the GUI opens its own window
          strip=False, upx=False, runtime_tmpdir=None,
          icon="dfcc.ico")
