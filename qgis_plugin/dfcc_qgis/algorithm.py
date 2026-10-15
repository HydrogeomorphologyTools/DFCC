import os
from qgis.PyQt.QtGui import QColor
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer, QgsProcessingParameterNumber,
                       QgsProcessingParameterBoolean, QgsProcessingParameterFolderDestination, QgsProcessingParameterEnum,
                       QgsProcessingContext, QgsProcessingUtils, QgsRasterLayer, QgsVectorLayer, QgsPalettedRasterRenderer,
                       QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsLineSymbol, QgsProject, QgsProcessingException)

COLORS = {1: "#1f5fbf", 2: "#d62828", 3: "#f77f00", 4: "#2a9d3c"}
NAMES = {1: "propagation", 2: "initiation", 3: "slowing", 4: "stop"}


class DfccAlgorithm(QgsProcessingAlgorithm):
    DTM, OUT = "DTM", "OUTDIR"
    _loaded = []

    def name(self):
        return "dfcc"

    def displayName(self):
        return "DFCC - channel classification, initiation density, runout"

    def group(self):
        return "Debris flows"

    def groupId(self):
        return "debrisflow"

    def createInstance(self):
        return DfccAlgorithm()

    def shortHelpString(self):
        return ("Stand-alone Procedura DF: classifies the channel network (initiation, propagation, slowing, stop), "
                "computes the initiation-point kernel density and the high-density areas (2-class natural breaks). Optional: per-basin "
                "main channel with morphometric stop/restart analysis, and initiation points for MSF-type models.")

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.DTM, "DTM"))
        self.addParameter(QgsProcessingParameterNumber("THR", "Slope-area threshold", QgsProcessingParameterNumber.Double, 50.0))
        self.addParameter(QgsProcessingParameterBoolean("PREFILL", "Fill depressions (pre-processing)", False))
        self.addParameter(QgsProcessingParameterNumber("KD", "Kernel density radius (m)", QgsProcessingParameterNumber.Double, 50.0))
        self.addParameter(QgsProcessingParameterBoolean("RUNOUT", "Main channels, runout and MSF points", True))
        self.addParameter(QgsProcessingParameterNumber("MINA", "Min basin area (km2)", QgsProcessingParameterNumber.Double, 1.0))
        self.addParameter(QgsProcessingParameterNumber("MAXA", "Max basin area (km2)", QgsProcessingParameterNumber.Double, 20.0))
        self.addParameter(QgsProcessingParameterNumber("SPLA", "Split at confluences (km2)", QgsProcessingParameterNumber.Double, 2.0))
        self.addParameter(QgsProcessingParameterNumber("FAC", "Energy factor (K > f*L)", QgsProcessingParameterNumber.Double, 0.4))
        self.addParameter(QgsProcessingParameterNumber("RST", "Spurious restart if shorter than (m)", QgsProcessingParameterNumber.Double, 30.0))
        self.addParameter(QgsProcessingParameterBoolean("WNET", "Whole network runout (all channels, worst-case merge)", False))
        self.addParameter(QgsProcessingParameterNumber("EXT", "Extend profile past outlet (m, 0 = off)", QgsProcessingParameterNumber.Double, 0.0))
        self.addParameter(QgsProcessingParameterEnum("BRANCH", "Main channel", ["largest contributing area", "longest upstream path", "highest source"], defaultValue=0))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUT, "Output folder"))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            from dfcc import pipeline, part2
        except ImportError:
            return self._run_exe(parameters, context, feedback)
        lyr = self.parameterAsRasterLayer(parameters, self.DTM, context)
        out = self.parameterAsString(parameters, self.OUT, context)
        par = pipeline.Params(lyr.source(), out, self.parameterAsDouble(parameters, "THR", context), None,
                              self.parameterAsBool(parameters, "PREFILL", context), self.parameterAsDouble(parameters, "KD", context),
                              write_network=True)
        do_run = self.parameterAsBool(parameters, "RUNOUT", context)
        res = pipeline.run(par, log=feedback.pushInfo, progress=lambda f, m: feedback.setProgress(int(f * (80 if do_run else 100))))
        files = dict(res.files)
        if do_run:
            rp = part2.RunoutParams(self.parameterAsDouble(parameters, "MINA", context), self.parameterAsDouble(parameters, "MAXA", context),
                                    self.parameterAsDouble(parameters, "SPLA", context), self.parameterAsDouble(parameters, "FAC", context),
                                    self.parameterAsDouble(parameters, "RST", context),
                                    ["area", "longest", "highest"][self.parameterAsEnum(parameters, "BRANCH", context)],
                                    extend_downstream_m=self.parameterAsDouble(parameters, "EXT", context),
                                    whole_network=self.parameterAsBool(parameters, "WNET", context))
            o = part2.analyse(res, rp, out, log=feedback.pushInfo)
            files.update(o["files"])
        feedback.setProgress(100)
        DfccAlgorithm._loaded = [(k, v) for k, v in files.items() if v.lower().endswith((".tif", ".shp"))]
        self._ctx = context
        return {self.OUT: out}

    def _run_exe(self, parameters, context, feedback):
        """Fallback when the python package is not installed: call the stand-alone DFCC executable (env DFCC_EXE or PATH)."""
        import shutil, subprocess
        exe = os.environ.get("DFCC_EXE") or shutil.which("DFCC") or shutil.which("dfcc")
        if not exe:
            raise QgsProcessingException("Neither the python package 'dfcc' (pip install dfcc) nor the DFCC executable (set DFCC_EXE or add it to PATH) was found.")
        lyr = self.parameterAsRasterLayer(parameters, self.DTM, context)
        out = self.parameterAsString(parameters, self.OUT, context)
        g = lambda k: str(self.parameterAsDouble(parameters, k, context))
        cmd = [exe, "run", lyr.source(), "-o", out, "-t", g("THR"), "--kd-radius", g("KD")]
        if self.parameterAsBool(parameters, "PREFILL", context):
            cmd.append("--prefill")
        if self.parameterAsBool(parameters, "RUNOUT", context):
            cmd += ["--runout", "--min-area", g("MINA"), "--max-area", g("MAXA"), "--split-area", g("SPLA"),
                    "--energy-factor", g("FAC"), "--min-restart-len", g("RST"),
                    "--main-branch", ["area", "longest", "highest"][self.parameterAsEnum(parameters, "BRANCH", context)],
                    "--extend-downstream", g("EXT")] + (["--whole-network"] if self.parameterAsBool(parameters, "WNET", context) else [])
        feedback.pushInfo(" ".join(cmd))
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            feedback.pushInfo(line.rstrip())
        if proc.wait() != 0:
            raise QgsProcessingException("DFCC executable failed (exit code %d)" % proc.returncode)
        loaded = []
        for f in sorted(os.listdir(out)):
            stem, ext = os.path.splitext(f)
            if ext.lower() == ".shp":
                loaded.append((stem, os.path.join(out, f)))
            elif ext.lower() == ".tif":
                loaded.append(("HighDensity_raster" if stem == "HighDensity" else stem, os.path.join(out, f)))
        DfccAlgorithm._loaded = loaded
        return {self.OUT: out}

    def postProcessAlgorithm(self, context, feedback):
        proj = QgsProject.instance()
        for key, path in DfccAlgorithm._loaded:
            if not os.path.exists(path):
                continue
            if path.lower().endswith(".tif"):
                if key not in ("ClassifiedNetwork", "InitiationDensity", "HighDensity_raster"):
                    continue
                lyr = QgsRasterLayer(path, key)
                if key == "ClassifiedNetwork":
                    lyr.setRenderer(QgsPalettedRasterRenderer(lyr.dataProvider(), 1, [
                        QgsPalettedRasterRenderer.Class(k, QColor(COLORS[k]), NAMES[k]) for k in (2, 1, 3, 4)]))
            else:
                lyr = QgsVectorLayer(path, key, "ogr")
                if key == "Network_classes":
                    cats = [QgsRendererCategory(k, QgsLineSymbol.createSimple({"color": COLORS[k], "width": "0.9"}), NAMES[k]) for k in (2, 1, 3, 4)]
                    lyr.setRenderer(QgsCategorizedSymbolRenderer("class", cats))
                elif key in ("Runout_mainchannel", "Runout_network"):
                    wd = "1.2" if key == "Runout_mainchannel" else "0.7"
                    PH = {2: ("#1f6feb", "Runout: flow"), 3: ("#f77f00", "Stop"), 4: ("#6ec6ff", "Stopped, flow resumes downstream"),
                          5: ("#2a9d3c", "After final stop"), 1: ("#ffd60a", "Not activated")}
                    cats = [QgsRendererCategory(k, QgsLineSymbol.createSimple({"color": c, "width": wd}), n) for k, (c, n) in PH.items()]
                    lyr.setRenderer(QgsCategorizedSymbolRenderer("phase", cats))
            if lyr.isValid():
                proj.addMapLayer(lyr)
        return {}
