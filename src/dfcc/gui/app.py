"""DFCC graphical interface (PySide6 + matplotlib)."""
from __future__ import annotations
import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QDockWidget, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QFileDialog, QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox, QTabWidget,
                               QPlainTextEdit, QProgressBar, QScrollArea, QTableWidget, QTableWidgetItem, QMessageBox,
                               QHeaderView, QSizePolicy)
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from .. import __version__, pipeline, part2, config, viz
from . import theme
from .. import warmup


class Worker(QObject):
    progress = Signal(float, str)
    log = Signal(str)
    done = Signal(object, object)
    failed = Signal(str)

    def __init__(self, par, rp, do_runout):
        super().__init__()
        self.par, self.rp, self.do_runout = par, rp, do_runout

    def run(self):
        try:
            res = pipeline.run(self.par, log=self.log.emit, progress=lambda f, m: self.progress.emit(f * (0.8 if self.do_runout else 1.0), m))
            out = None
            if self.do_runout:
                self.progress.emit(0.85, "Main channels and runout")
                out = part2.analyse(res, self.rp, self.par.outdir, self.par.prefix, log=self.log.emit)
                self.progress.emit(1.0, "Done")
            self.done.emit(res, out)
        except Exception:
            self.failed.emit(traceback.format_exc())


class MplTab(QWidget):
    def __init__(self, figsize=(8, 6)):
        super().__init__()
        self.fig = Figure(figsize=figsize, facecolor=viz.PALETTE["bg"])
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.tb = NavigationToolbar2QT(self.canvas, self)
        self.tb.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.tb)
        lay.addWidget(self.canvas, 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"DFCC {__version__} - Debris-Flow Channel Classification")
        self.setWindowIcon(theme.app_icon())
        self.resize(1480, 900)
        self.res = None
        self.out = None
        self._thread = None
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._header())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._side())
        body.addWidget(self._center(), 1)
        lay.addLayout(body, 1)
        self.pb = QProgressBar()
        self.pb.setMaximumWidth(320)
        self.pb.setRange(0, 1000)
        self.statusBar().addPermanentWidget(self.pb)
        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------ layout
    def _header(self):
        h = QWidget(objectName="header")
        h.setFixedHeight(84)
        l = QHBoxLayout(h)
        l.setContentsMargins(18, 8, 18, 8)
        ic = QLabel()
        ic.setPixmap(theme.logo_pixmap(64))
        l.addWidget(ic)
        t = QVBoxLayout()
        t.setSpacing(0)
        t.addWidget(QLabel("DFCC", objectName="title"))
        t.addWidget(QLabel("Debris-Flow Channel Classification  ·  initiation, propagation and stopping of debris flows", objectName="subtitle"))
        l.addLayout(t)
        l.addStretch(1)
        v = QLabel(f"v{__version__}  ·  FOSS  ·  GPL-2.0+")
        v.setObjectName("subtitle")
        l.addWidget(v)
        hb = QPushButton("?  Help")
        hb.setToolTip("Illustrated documentation (F1)")
        hb.setShortcut("F1")
        hb.clicked.connect(self.show_help)
        l.addWidget(hb)
        return h

    def _on_progress(self, f, m):
        self.pb.setValue(int(f * 1000))
        self.statusBar().showMessage(m)

    def log_line(self, msg):
        import time as _t
        self.logw.appendPlainText(f"[{_t.strftime('%H:%M:%S')}] {msg}")

    def _save_log(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save log", "dfcc_log.txt", "Text (*.txt)")
        if p:
            Path(p).write_text(self.logw.toPlainText(), encoding="utf-8")

    def _sync3d(self, on):
        for c in (self.p3d, self.m3d):
            if c.isChecked() != on:
                c.blockSignals(True); c.setChecked(on); c.blockSignals(False)
        self.draw_profile()
        self.draw_matrix()

    def draw_matrix(self):
        self.mat.fig.clf()
        if self.out and self.mat_chk.isChecked():
            self.log_line("Drawing profile matrix…")
            viz.profile_matrix(self.mat.fig, self.out, self.mat_cols.value(), show3d=self.m3d.isChecked())
        else:
            self.mat.fig.patch.set_facecolor(viz.PALETTE["bg"])
        self.mat.canvas.draw_idle()

    def show_help(self):
        from .help import HelpDialog
        if getattr(self, "_help", None) is None:
            self._help = HelpDialog(self)
        self._help.show(); self._help.raise_()

    def _row(self, edit, btn_text, slot):
        w = QWidget()
        r = QHBoxLayout(w)
        r.setContentsMargins(0, 0, 0, 0)
        r.addWidget(edit, 1)
        b = QPushButton(btn_text)
        b.setFixedWidth(34)
        b.clicked.connect(slot)
        r.addWidget(b)
        return w

    def _dspin(self, v, lo, hi, step=1.0, dec=2, suffix=""):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(dec)
        s.setSingleStep(step)
        s.setValue(v)
        s.setSuffix(suffix)
        return s

    def _side(self):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFixedWidth(400)
        w = QWidget(objectName="side")
        sc.setWidget(w)
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(6)

        g = QGroupBox("1 · Data")
        f = QFormLayout(g)
        self.dtm = QLineEdit()
        self.dtm.setPlaceholderText("DTM GeoTIFF (projected CRS, square cells)")
        self.dtm.editingFinished.connect(self._dtm_info)
        f.addRow("DTM", self._row(self.dtm, "…", self._pick_dtm))
        self.outdir = QLineEdit()
        f.addRow("Output", self._row(self.outdir, "…", self._pick_out))
        self.prefix = QLineEdit()
        self.prefix.setPlaceholderText("(optional)")
        f.addRow("Prefix", self.prefix)
        self.info = QLabel("")
        self.info.setObjectName("subtitle")
        self.info.setWordWrap(True)
        f.addRow(self.info)
        v.addWidget(g)

        g = QGroupBox("2 · DF procedure")
        f = QFormLayout(g)
        self.thr = self._dspin(50, 1, 1e6, 5, 1)
        self.thr.setToolTip("Slope-area threshold for channel extraction (S^m · A^n)")
        f.addRow("Channel threshold", self.thr)
        self.res_auto = QCheckBox("cell size from DTM")
        self.res_auto.setChecked(True)
        self.resv = self._dspin(5, 0.1, 1000, 0.5, 2, " m")
        self.resv.setEnabled(False)
        self.res_auto.toggled.connect(lambda c: self.resv.setEnabled(not c))
        f.addRow(self.res_auto, self.resv)
        self.kd = self._dspin(50, 5, 1000, 5, 1, " m")
        f.addRow("Kernel density radius", self.kd)
        self.prefill = QCheckBox("Fill depressions (pre-processing)")
        f.addRow(self.prefill)
        self.keep = QCheckBox("Save intermediate rasters")
        f.addRow(self.keep)
        v.addWidget(g)

        g = QGroupBox("3 · Main channels and runout")
        g.setCheckable(True)
        g.setChecked(True)
        self.g_run = g
        f = QFormLayout(g)
        self.minA = self._dspin(1.0, 0.0, 1e4, 0.1, 2, " km²")
        self.maxA = self._dspin(20.0, 0.1, 1e5, 1, 1, " km²")
        self.splA = self._dspin(2.0, 0.0, 1e4, 0.5, 2, " km²")
        self.splA.setToolTip("Confluences where both branches exceed this area split the basin in two")
        f.addRow("Min basin area", self.minA)
        f.addRow("Max basin area", self.maxA)
        f.addRow("Split at confluences", self.splA)
        self.pp = QLineEdit()
        self.pp.setPlaceholderText("point shapefile (optional)")
        f.addRow("Pour points", self._row(self.pp, "…", self._pick_pp))
        self.branch = QComboBox()
        self.branch.addItem("largest contributing area", "area")
        self.branch.addItem("longest upstream path", "longest")
        self.branch.addItem("highest source", "highest")
        f.addRow("Main channel", self.branch)
        self.fac = self._dspin(0.4, 0.01, 5, 0.05, 2)
        self.fac.setToolTip("Stop when distance in classes 3/4 > factor × drop in classes 1/2")
        f.addRow("Energy factor", self.fac)
        self.rst = self._dspin(30, 0, 1e4, 5, 0, " m")
        self.rst.setToolTip("Restarts dying within this length are 'spurious'")
        f.addRow("Spurious restart <", self.rst)
        self.ext = self._dspin(0, 0, 1e5, 50, 0, " m")
        self.ext.setToolTip("Continue the profile past the basin outlet along the network (e.g. over the fan); 0 = off")
        f.addRow("Extend past outlet", self.ext)
        self.wnet = QCheckBox("Whole network runout")
        self.wnet.setToolTip("Apply the energy rule to every channel of the selected basins (not only the main channel). "
                             "At confluences the locally worst condition (largest energy margin 0.4·L − K) is propagated. Off by default.")
        f.addRow(self.wnet)
        self.head = QCheckBox("Start at head even without initiation cell")
        f.addRow(self.head)
        self.hot = QCheckBox("Initiation points for MSF")
        self.hot.setChecked(True)
        f.addRow(self.hot)
        self.hsnap = self._dspin(50, 0, 1000, 5, 0, " m")
        f.addRow("Point snap", self.hsnap)
        self.prune = QCheckBox("Prune aligned downstream points")
        self.prune.setChecked(True)
        f.addRow(self.prune)
        v.addWidget(g)

        row = QHBoxLayout()
        b1 = QPushButton("Save config…")
        b1.clicked.connect(self._save_cfg)
        b2 = QPushButton("Load config…")
        b2.clicked.connect(self._load_cfg)
        row.addWidget(b1)
        row.addWidget(b2)
        v.addLayout(row)
        self.btn = QPushButton("▶  Run DFCC", objectName="run")
        self.btn.clicked.connect(self.start)
        v.addWidget(self.btn)
        b3 = QPushButton("Open output folder")
        b3.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.outdir.text() or ".")))
        v.addWidget(b3)
        v.addStretch(1)
        return sc

    def _center(self):
        self.tabs = QTabWidget()
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setContentsMargins(10, 6, 10, 0)
        self.chk = {}
        for key, txt, on in (("net", "Classified network", True), ("dens", "Initiation density", True), ("high", "High density", True),
                             ("run", "Main channel runout", True), ("wnet", "Whole network runout", True), ("pts", "MSF points", True)):
            c = QCheckBox(txt)
            c.setChecked(on)
            c.toggled.connect(self.redraw)
            self.chk[key] = c
            top.addWidget(c)
        top.addStretch(1)
        l.addLayout(top)
        self.map = MplTab()
        l.addWidget(self.map, 1)
        self.tabs.addTab(w, "Map")
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(6, 6, 6, 0)
        prow = QHBoxLayout()
        self.bsel = QComboBox()
        self.bsel.currentIndexChanged.connect(self.draw_profile)
        prow.addWidget(self.bsel, 1)
        self.p3d = QCheckBox("Overlay 3-D distance")
        self.p3d.setToolTip("Adds the same profile against the 3-D (slope) distance, dashed, in the same plot")
        self.p3d.toggled.connect(self._sync3d)
        prow.addWidget(self.p3d)
        pl.addLayout(prow)
        self.prof = MplTab((8, 4))
        pl.addWidget(self.prof, 1)
        self.tabs.addTab(pw, "Profile")
        mw = QWidget()
        ml = QVBoxLayout(mw)
        ml.setContentsMargins(6, 6, 6, 0)
        mt = QHBoxLayout()
        self.mat_chk = QCheckBox("Show profile matrix (all basins)")
        self.mat_chk.setToolTip("Optional: draws one small profile per basin (can be slow with many basins)")
        self.mat_chk.toggled.connect(self.draw_matrix)
        mt.addWidget(self.mat_chk)
        self.m3d = QCheckBox("Overlay 3-D distance")
        self.m3d.toggled.connect(self._sync3d)
        mt.addWidget(self.m3d)
        mt.addWidget(QLabel("columns"))
        self.mat_cols = QSpinBox()
        self.mat_cols.setRange(1, 6); self.mat_cols.setValue(3)
        self.mat_cols.valueChanged.connect(self.draw_matrix)
        mt.addWidget(self.mat_cols)
        mt.addStretch(1)
        ml.addLayout(mt)
        self.mat = MplTab((9, 6))
        ml.addWidget(self.mat, 1)
        self.tabs.addTab(mw, "Profile matrix")
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabs.addTab(self.table, "Basin summary")
        # verbose console (always visible, dockable)
        self.logw = QPlainTextEdit()
        self.logw.setReadOnly(True)
        self.logw.setMaximumBlockCount(20000)
        self.logw.setFont(QFont("Consolas", 9))
        self.logw.setPlaceholderText("Detailed progress appears here…")
        dock = QDockWidget("Console", self)
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(4, 4, 4, 4)
        cl.addWidget(self.logw)
        cb = QHBoxLayout()
        bclr = QPushButton("Clear"); bclr.clicked.connect(self.logw.clear)
        bsv = QPushButton("Save log…"); bsv.clicked.connect(self._save_log)
        cb.addStretch(1); cb.addWidget(bclr); cb.addWidget(bsv)
        cl.addLayout(cb)
        dock.setWidget(cw)
        dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        dock.setMinimumHeight(150)
        self.console_dock = dock
        self.ax = self.map.fig.add_subplot(111)
        self._empty_map()
        return self.tabs

    def _empty_map(self):
        self.ax.clear()
        self.ax.set_facecolor(viz.PALETTE["bg"])
        self.ax.text(0.5, 0.5, "Load a DTM and run the procedure", color=viz.PALETTE["muted"], ha="center", va="center",
                     transform=self.ax.transAxes, fontsize=13)
        self.ax.set_xticks([]); self.ax.set_yticks([])
        for s in self.ax.spines.values():
            s.set_visible(False)
        self.map.canvas.draw_idle()

    # ----------------------------------------------------------------- helpers
    def _pick_dtm(self):
        p, _ = QFileDialog.getOpenFileName(self, "DTM", "", "Raster (*.tif *.tiff *.asc *.img);;All (*)")
        if p:
            self.dtm.setText(p)
            if not self.outdir.text():
                self.outdir.setText(str(Path(p).parent / "DFCC_output"))
            self._dtm_info()

    def _pick_out(self):
        p = QFileDialog.getExistingDirectory(self, "Output folder")
        if p:
            self.outdir.setText(p)

    def _pick_pp(self):
        p, _ = QFileDialog.getOpenFileName(self, "Pour points", "", "Shapefile (*.shp)")
        if p:
            self.pp.setText(p)

    def _dtm_info(self):
        try:
            from .. import io as dio
            g = dio.read_raster(self.dtm.text())
            self.info.setText(f"{g.shape[1]} × {g.shape[0]} cells · cell {g.cell:g} m · {'CRS ok' if g.wkt else 'CRS missing'}")
            self.resv.setValue(g.cell)
        except Exception as e:
            self.info.setText(f"⚠ {e}")

    def params(self):
        par = pipeline.Params(self.dtm.text(), self.outdir.text(), self.thr.value(),
                              None if self.res_auto.isChecked() else self.resv.value(), self.prefill.isChecked(), self.kd.value(),
                              keep_intermediate=self.keep.isChecked(), write_network=True, prefix=self.prefix.text())
        pps = None
        if self.pp.text():
            import shapefile
            pps = [tuple(s.points[0]) for s in shapefile.Reader(self.pp.text()).shapes()]
        rp = part2.RunoutParams(self.minA.value(), self.maxA.value(), self.splA.value(), self.fac.value(), self.rst.value(),
                                self.branch.currentData(), self.head.isChecked(), pps, hotspot_snap_m=self.hsnap.value(),
                                hotspot_prune=self.prune.isChecked(), write_hotspots=self.hot.isChecked(),
                                extend_downstream_m=self.ext.value(), whole_network=self.wnet.isChecked())
        return par, rp, self.g_run.isChecked()

    def set_params(self, par, rp, en):
        self.dtm.setText(par.dtm); self.outdir.setText(par.outdir); self.prefix.setText(par.prefix)
        self.thr.setValue(par.threshold)
        self.res_auto.setChecked(par.resolution is None)
        if par.resolution:
            self.resv.setValue(par.resolution)
        self.kd.setValue(par.kd_radius); self.prefill.setChecked(par.prefill); self.keep.setChecked(par.keep_intermediate)
        self.g_run.setChecked(en)
        self.minA.setValue(rp.min_area_km2); self.maxA.setValue(rp.max_area_km2); self.splA.setValue(rp.split_area_km2)
        self.fac.setValue(rp.energy_factor); self.rst.setValue(rp.min_restart_len_m)
        self.branch.setCurrentIndex(max(0, self.branch.findData(rp.main_branch)))
        self.head.setChecked(rp.start_at_head); self.hot.setChecked(rp.write_hotspots)
        self.wnet.setChecked(rp.whole_network); self.ext.setValue(rp.extend_downstream_m); self.hsnap.setValue(rp.hotspot_snap_m); self.prune.setChecked(rp.hotspot_prune)
        self._dtm_info()

    def _save_cfg(self):
        p, _ = QFileDialog.getSaveFileName(self, "Save configuration", "dfcc_config.json", "JSON (*.json)")
        if p:
            config.save(p, *self.params())
            self.statusBar().showMessage(f"Configuration saved: {p}")

    def _load_cfg(self):
        p, _ = QFileDialog.getOpenFileName(self, "Load configuration", "", "JSON (*.json)")
        if p:
            try:
                self.set_params(*config.load(p))
                self.statusBar().showMessage(f"Configuration loaded: {p}")
            except Exception as e:
                QMessageBox.warning(self, "Configuration", str(e))

    # --------------------------------------------------------------------- run
    def start(self):
        if not self.dtm.text() or not self.outdir.text():
            QMessageBox.information(self, "DFCC", "Select a DTM and an output folder.")
            return
        try:
            par, rp, en = self.params()
        except Exception as e:
            QMessageBox.warning(self, "Parameters", str(e))
            return
        self.logw.clear()
        self.log_line(f"DFCC {__version__} - run started | DTM {par.dtm}")
        self.btn.setEnabled(False)
        self.pb.setValue(0)
        if not warmup._done:                              # compile numba kernels in the main thread (safe on Windows)
            self.log_line("Compiling / loading numerical kernels (first run only, may take a minute)…")
            self.statusBar().showMessage("Preparing numerical kernels (first run only, may take a minute)…")
            self.btn.setText("Compiling kernels…")
            QApplication.processEvents()
            warmup.warmup()
            self.log_line("Kernels ready.")
            self.btn.setText("▶  Run DFCC")
        self._thread = QThread()
        self._thread.setStackSize(256 * 1024 * 1024)      # Windows QThreads default to a tiny stack; numba kernels need room
        self.worker = Worker(par, rp, en)
        self.worker.moveToThread(self._thread)
        self._thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log_line, Qt.QueuedConnection)
        self.worker.progress.connect(self._on_progress, Qt.QueuedConnection)
        self.worker.done.connect(self.finished, Qt.QueuedConnection)
        self.worker.failed.connect(self.failed, Qt.QueuedConnection)
        self._thread.start()

    def failed(self, tb):
        self._thread.quit()
        self.btn.setEnabled(True)
        self.logw.appendPlainText(tb)
        self.tabs.setCurrentIndex(3)
        QMessageBox.critical(self, "Error", tb.splitlines()[-1])

    def finished(self, res, out):
        self._thread.quit()
        self.btn.setEnabled(True)
        self.res, self.out = res, out
        self.statusBar().showMessage("Completed")
        self.redraw()
        self.fill_table()
        self.bsel.blockSignals(True)
        self.bsel.clear()
        if out:
            for s in out["summary"]:
                self.bsel.addItem(f"Basin {s['basin']} · {s['area_km2']} km² · {s['length_m']:.0f} m", s["basin"])
        self.bsel.blockSignals(False)
        self.draw_profile()
        self.draw_matrix()

    def redraw(self):
        if self.res is None:
            return
        ax = self.ax
        self.map.fig.clf()
        ax = self.ax = self.map.fig.add_subplot(111)
        viz.draw_base(ax, self.res)
        if self.chk["dens"].isChecked():
            viz.draw_density(ax, self.res, 0.5)
        if self.chk["high"].isChecked():
            viz.draw_high(ax, self.res)
        show_cls = self.chk["net"].isChecked()
        run_on = bool(self.out and (self.chk["run"].isChecked() or (self.out.get("network") and self.chk["wnet"].isChecked())))
        if show_cls:
            viz.draw_network(ax, self.res, alpha=0.45 if run_on else 1.0)   # dimmed under the runout layers
        seen = net_seen = None
        if self.out and self.chk["run"].isChecked():
            seen = viz.draw_runout(ax, self.out, 3.2 if (self.out.get("network") and self.chk["wnet"].isChecked()) else 2.6)
        if self.out and self.out.get("network") and self.chk["wnet"].isChecked():
            net_seen = viz.draw_network_runout(ax, self.out)
        viz.side_legend(ax, classes=show_cls, runout=seen, network=net_seen,
                        msf=bool(self.out and self.chk["pts"].isChecked() and self.out["hotspots"]))
        if self.out and self.chk["pts"].isChecked() and self.out["hotspots"]:
            g = self.res.grid
            xy = [g.xy(d["row"], d["col"]) for d in self.out["hotspots"] if d["keep"]]
            ax.scatter([a for a, b in xy], [b for a, b in xy], s=14, c="#ffd166", edgecolors="k", linewidths=0.3, zorder=9)
        self.map.fig.tight_layout()
        self.map.canvas.draw_idle()

    def draw_profile(self):
        self.prof.fig.clf()
        if self.out and self.bsel.count():
            viz.profile_figure(self.prof.fig, self.out, self.bsel.currentData(), show3d=self.p3d.isChecked())
        self.prof.canvas.draw_idle()

    def fill_table(self):
        if not self.out or not self.out["summary"]:
            self.table.clear(); self.table.setRowCount(0); return
        rows = self.out["summary"]
        keys = list(rows[0].keys())
        self.table.setColumnCount(len(keys))
        self.table.setRowCount(len(rows))
        self.table.setHorizontalHeaderLabels(keys)
        for i, r in enumerate(rows):
            for j, k in enumerate(keys):
                self.table.setItem(i, j, QTableWidgetItem("" if r[k] is None else str(r[k])))
        self.table.resizeColumnsToContents()


def main(argv=None):
    if sys.platform == "win32":                 # own taskbar identity/icon instead of the generic python one
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CNR.GEO.DFCC")
        except Exception:
            pass
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setStyleSheet(theme.QSS)
    app.setWindowIcon(theme.app_icon())
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
