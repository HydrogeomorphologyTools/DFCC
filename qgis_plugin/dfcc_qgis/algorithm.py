import os
from qgis.PyQt.QtGui import QColor
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer, QgsProcessingParameterNumber,
                       QgsProcessingParameterBoolean, QgsProcessingParameterFolderDestination, QgsProcessingParameterEnum,
                       QgsProcessingParameterDefinition, QgsProcessingContext, QgsProcessingUtils, QgsRasterLayer, QgsVectorLayer,
                       QgsPalettedRasterRenderer, QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsLineSymbol, QgsProject,
                       QgsProcessingException)

COLORS = {1: "#1f5fbf", 2: "#d62828", 3: "#f77f00", 4: "#2a9d3c"}
NAMES = {1: "propagation", 2: "initiation", 3: "slowing", 4: "stop"}
GEN_METHODS = ["average", "median", "bilinear", "cubic"]
# advanced numeric parameters: (key, label, default, Params field, CLI option); defaults = original Procedura DF
ADVANCED = [("SEXP", "Channel extraction: slope exponent m (S^m*A^n)", 1.0, "slope_exp", "--slope-exp"),
            ("AEXP", "Channel extraction: area exponent n (S^m*A^n, A in cells)", 0.5, "area_exp", "--area-exp"),
            ("WBK", "Initiation: coefficient k (S > k*A^e, A in km2)", 0.32, "wb_k", "--wb-k"),
            ("WBE", "Initiation: exponent e (S > k*A^e)", -0.2, "wb_exp", "--wb-exp"),
            ("AMAX", "Initiation only where A < (km2)", 20.0, "area_max_km2", "--max-init-area"),
            ("SSLOW", "Propagation / slowing slope boundary (m/m, 0.1405 = 8 deg)", 0.1405, "s_dep_max", "--s-slow"),
            ("SSTOP", "Slowing / stop slope boundary (m/m, 0.0524 = 3 deg)", 0.0524, "s_stop", "--s-stop"),
            ("SMAX", "Max slope classified (m/m, 0.7812 = 38 deg)", 0.7812, "s_max", "--s-max")]


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
                "main channel with morphometric stop/restart analysis, and initiation points for MSF-type models.<br><br>"
                "<b>Advanced parameters.</b> The defaults reproduce the original Procedura DF. Its thresholds come from "
                "literature based on ~10 m (non-LiDAR) DTMs and assume reach-scale slopes; very fine DTMs resolve local steps "
                "(boulders, check dams) that alter slopes and classes. Consider generalizing the DTM (e.g. to 5-10 m) and change "
                "the thresholds only after calibration. The channel threshold uses A in cells: when generalizing it is rescaled "
                "to keep the same S^m*A^n with A in m2, unless told otherwise.")

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
        adv = [QgsProcessingParameterNumber("GEN", "Generalize the DTM to this cell size (m, 0 = off; pre-processing)",
                                            QgsProcessingParameterNumber.Double, 0.0, minValue=0.0),
               QgsProcessingParameterEnum("GENM", "Generalization method", GEN_METHODS, defaultValue=0),
               QgsProcessingParameterBoolean("GENKEEP", "Generalization: keep the channel threshold as is (no rescaling)", False)]
        adv += [QgsProcessingParameterNumber(k, lab, QgsProcessingParameterNumber.Double, d) for k, lab, d, _, _ in ADVANCED]
        for p in adv:
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUT, "Output folder"))

    def _advanced(self, parameters, context):
        """Advanced settings as pipeline.Params keyword arguments."""
        gen = self.parameterAsDouble(parameters, "GEN", context)
        kw = {f: self.parameterAsDouble(parameters, k, context) for k, _, _, f, _ in ADVANCED}
        kw.update(generalize_cell=gen if gen > 0 else None,
                  generalize_method=GEN_METHODS[self.parameterAsEnum(parameters, "GENM", context)],
                  generalize_rescale_threshold=not self.parameterAsBool(parameters, "GENKEEP", context))
        return kw

    def processAlgorithm(self, parameters, context, feedback):
        try:
            from dfcc import pipeline, part2
        except ImportError:
            return self._run_exe(parameters, context, feedback)
        lyr = self.parameterAsRasterLayer(parameters, self.DTM, context)
        out = self.parameterAsString(parameters, self.OUT, context)
        par = pipeline.Params(lyr.source(), out, self.parameterAsDouble(parameters, "THR", context), None,
                              self.parameterAsBool(parameters, "PREFILL", context), self.parameterAsDouble(parameters, "KD", context),
                              write_network=True, **self._advanced(parameters, context))
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
            raise QgsProcessingException("Neither the python package 'dfcc' (pip install \"dfcc @ git+https://github.com/HydrogeomorphologyTools/DFCC\") nor the DFCC executable (set DFCC_EXE or add it to PATH) was found.")
        lyr = self.parameterAsRasterLayer(parameters, self.DTM, context)
        out = self.parameterAsString(parameters, self.OUT, context)
        g = lambda k: str(self.parameterAsDouble(parameters, k, context))
        cmd = [exe, "run", lyr.source(), "-o", out, "-t", g("THR"), "--kd-radius", g("KD")]
        if self.parameterAsBool(parameters, "PREFILL", context):
            cmd.append("--prefill")
        kw = self._advanced(parameters, context)
        for _, _, d, f, opt in ADVANCED:
            if kw[f] != d:                  # only non-default values: keeps working with older DFCC executables
                cmd += [opt, str(kw[f])]
        if kw["generalize_cell"]:
            cmd += ["--generalize", str(kw["generalize_cell"]), "--generalize-method", kw["generalize_method"]]
            if not kw["generalize_rescale_threshold"]:
                cmd.append("--generalize-keep-threshold")
        if self.parameterAsBool(parameters, "RUNOUT", context):
            cmd += ["--runout", "--min-area", g("MINA"), "--max-area", g("MAXA"), "--split-area", g("SPLA"),
                    "--energy-factor", g("FAC"), "--min-restart-len", g("RST"),
                    "--main-branch", ["area", "longest", "highest"][self.parameterAsEnum(parameters, "BRANCH", context)],
                    "--extend-downstream", g("EXT")] + (["--whole-network"] if self.parameterAsBool(parameters, "WNET", context) else [])
        feedback.pushInfo(" ".join(cmd))
        env = {k: v for k, v in os.environ.items()      # QGIS' own PROJ/GDAL/Python settings must not leak into DFCC.exe
               if k.upper() not in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA", "GDAL_DRIVER_PATH", "PYTHONHOME", "PYTHONPATH")}
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
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
        loaded = [(k, p) for k, p in loaded if k != "DTM_generalized"]
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
