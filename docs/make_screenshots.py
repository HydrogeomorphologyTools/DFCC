"""Regenerate the GUI screenshots used in README.md (dark theme, offscreen Qt).

    cd examples/gadria && python ../../docs/make_screenshots.py
"""
import os
from pathlib import Path
from dfcc import pipeline, part2, config

OUT = Path(__file__).resolve().parent / "images"
par, rp, _ = config.load("dfcc_config.json")
par.outdir = "output"
res = pipeline.run(par, log=lambda *a: None)
out = part2.analyse(res, rp, par.outdir, log=lambda *a: None)
# --- GUI screenshots (dark theme)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDockWidget
from dfcc.gui import app as A, theme
from dfcc.gui.help import HelpDialog
qa = QApplication.instance() or QApplication([])
qa.setStyleSheet(theme.QSS)
w = A.MainWindow()
w._thread = type("T", (), {"quit": lambda s: None})()
w.set_params(par, rp, True)
for d in w.findChildren(QDockWidget):
    d.hide()
w.resize(1560, 940); w.show()
w.finished(res, out)
w.logw.appendPlainText("")
for i, name in enumerate(("map", "profile", "matrix", "summary")):
    w.tabs.setCurrentIndex(i); qa.processEvents(); w.grab().save(str(OUT / f"gui_{name}.png"))
h = HelpDialog(w); h.resize(1180, 820); h.show(); qa.processEvents(); h.grab().save(str(OUT / "gui_help.png"))
print("figures written to", OUT)
