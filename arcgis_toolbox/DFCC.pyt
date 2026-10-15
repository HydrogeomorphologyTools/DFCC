# -*- coding: utf-8 -*-
"""ArcGIS Pro Python toolbox for DFCC (Python 3 only; ArcMap 10.x runs Python 2.7 -> use the GUI/CLI instead).

Requires the package:  pip install "dfcc @ git+https://github.com/HydrogeomorphologyTools/DFCC"   (in the ArcGIS Pro python environment, e.g. a cloned env),
or keep this folder next to ../src of the source checkout."""
import os
import sys
import arcpy

GEN_METHODS = ["average", "median", "bilinear", "cubic"]
# advanced numeric parameters: (name, label, default, Params field, CLI option); defaults = original Procedura DF
ADVANCED = [("sexp", "Channel extraction: slope exponent m (S^m*A^n)", 1.0, "slope_exp", "--slope-exp"),
            ("aexp", "Channel extraction: area exponent n (S^m*A^n, A in cells)", 0.5, "area_exp", "--area-exp"),
            ("wbk", "Initiation: coefficient k (S > k*A^e, A in km2)", 0.32, "wb_k", "--wb-k"),
            ("wbe", "Initiation: exponent e (S > k*A^e)", -0.2, "wb_exp", "--wb-exp"),
            ("amax", "Initiation only where A < (km2)", 20.0, "area_max_km2", "--max-init-area"),
            ("sslow", "Propagation / slowing slope boundary (m/m, 0.1405 = 8 deg)", 0.1405, "s_dep_max", "--s-slow"),
            ("sstop", "Slowing / stop slope boundary (m/m, 0.0524 = 3 deg)", 0.0524, "s_stop", "--s-stop"),
            ("smax", "Max slope classified (m/m, 0.7812 = 38 deg)", 0.7812, "s_max", "--s-max")]
ADV_CATEGORY = "Advanced (defaults = Procedura DF, derived from ~10 m DTMs: change only after calibration)"


def _ensure():
    try:
        import dfcc  # noqa: F401
    except ImportError:
        here = os.path.dirname(os.path.abspath(__file__))
        src = os.path.abspath(os.path.join(here, "..", "src"))
        if os.path.isdir(os.path.join(src, "dfcc")):
            sys.path.insert(0, src)


class Toolbox(object):
    def __init__(self):
        self.label = "DFCC"
        self.alias = "dfcc"
        self.tools = [DFCCProcedure]


class DFCCProcedure(object):
    def __init__(self):
        self.label = "DFCC - Debris-Flow Channel Classification"
        self.description = ("Channel network classification (initiation / propagation / slowing / stop), initiation-point density, "
                            "per-basin main channels with morphometric stop distance and initiation points for MSF.")
        self.canRunInBackground = False

    def getParameterInfo(self):
        P = arcpy.Parameter
        p = [P("dtm", "DTM", "Input", "GPRasterLayer", "Required"),
             P("outdir", "Output folder", "Input", "DEFolder", "Required"),
             P("thr", "Slope-area threshold", "Input", "GPDouble", "Required"),
             P("prefill", "Fill depressions (pre-processing)", "Input", "GPBoolean", "Optional"),
             P("kd", "Kernel density radius (m)", "Input", "GPDouble", "Required"),
             P("runout", "Main channels, runout and MSF points", "Input", "GPBoolean", "Optional"),
             P("mina", "Min basin area (km2)", "Input", "GPDouble", "Optional"),
             P("maxa", "Max basin area (km2)", "Input", "GPDouble", "Optional"),
             P("spla", "Split at confluences (km2)", "Input", "GPDouble", "Optional"),
             P("fac", "Energy factor (K > f*L)", "Input", "GPDouble", "Optional"),
             P("rst", "Spurious restart if shorter than (m)", "Input", "GPDouble", "Optional"),
             P("branch", "Main channel criterion", "Input", "GPString", "Optional"),
             P("ext", "Extend profile past outlet (m, 0 = off)", "Input", "GPDouble", "Optional"),
             P("wnet", "Whole network runout (all channels, worst-case merge)", "Input", "GPBoolean", "Optional")]
        for prm, v in zip(p[2:], [50.0, False, 50.0, True, 1.0, 20.0, 2.0, 0.4, 30.0, "area", 0.0, False]):
            prm.value = v
        br = [q for q in p if q.name == "branch"][0]
        br.filter.type = "ValueList"
        br.filter.list = ["area", "longest", "highest"]
        adv = [P("gen", "Generalize the DTM to this cell size (m, 0 = off; pre-processing)", "Input", "GPDouble", "Optional"),
               P("genm", "Generalization method", "Input", "GPString", "Optional"),
               P("genkeep", "Generalization: keep the channel threshold as is (no rescaling)", "Input", "GPBoolean", "Optional")]
        adv[0].value, adv[1].value, adv[2].value = 0.0, "average", False
        adv[1].filter.type = "ValueList"
        adv[1].filter.list = GEN_METHODS
        for name, lab, d, _, _ in ADVANCED:
            q = P(name, lab, "Input", "GPDouble", "Optional")
            q.value = d
            adv.append(q)
        for q in adv:
            q.category = ADV_CATEGORY
        return p + adv

    @staticmethod
    def _advanced(v):
        """Advanced settings as pipeline.Params keyword arguments (empty fields fall back to the defaults)."""
        kw = {f: float(d if v.get(n) is None else v[n]) for n, _, d, f, _ in ADVANCED}
        gen = float(v.get("gen") or 0)
        kw.update(generalize_cell=gen if gen > 0 else None, generalize_method=str(v.get("genm") or "average"),
                  generalize_rescale_threshold=not bool(v.get("genkeep")))
        return kw

    def _run_exe(self, parameters, messages):
        """Fallback: call the stand-alone DFCC executable (env DFCC_EXE or PATH)."""
        import shutil, subprocess
        exe = os.environ.get("DFCC_EXE") or shutil.which("DFCC") or shutil.which("dfcc")
        if not exe:
            raise arcpy.ExecuteError("Python package 'dfcc' or DFCC.exe not found (set DFCC_EXE or add it to PATH).")
        v = {p.name: p.value for p in parameters}
        cmd = [exe, "run", arcpy.Describe(v["dtm"]).catalogPath, "-o", str(v["outdir"]), "-t", str(v["thr"]), "--kd-radius", str(v["kd"])]
        if v["prefill"]:
            cmd.append("--prefill")
        kw = self._advanced(v)
        for _, _, d, f, opt in ADVANCED:
            if kw[f] != d:                  # only non-default values: keeps working with older DFCC executables
                cmd += [opt, str(kw[f])]
        if kw["generalize_cell"]:
            cmd += ["--generalize", str(kw["generalize_cell"]), "--generalize-method", kw["generalize_method"]]
            if not kw["generalize_rescale_threshold"]:
                cmd.append("--generalize-keep-threshold")
        if v["runout"]:
            cmd += ["--runout", "--min-area", str(v["mina"]), "--max-area", str(v["maxa"]), "--split-area", str(v["spla"]),
                    "--energy-factor", str(v["fac"]), "--min-restart-len", str(v["rst"]),
                    "--main-branch", str(v["branch"] or "area"), "--extend-downstream", str(v["ext"] or 0)] + (["--whole-network"] if v["wnet"] else [])
        env = {k: v for k, v in os.environ.items()      # ArcGIS Pro's own PROJ/GDAL/Python settings must not leak into DFCC.exe
               if k.upper() not in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA", "GDAL_DRIVER_PATH", "PYTHONHOME", "PYTHONPATH")}
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=env)
        for line in p.stdout:
            messages.addMessage(line.rstrip())
        if p.wait() != 0:
            raise arcpy.ExecuteError("DFCC.exe failed")

    def execute(self, parameters, messages):
        _ensure()
        try:
            from dfcc import pipeline, part2
        except ImportError:
            return self._run_exe(parameters, messages)
        v = {p.name: p.value for p in parameters}
        dtm = arcpy.Describe(v["dtm"]).catalogPath
        par = pipeline.Params(dtm, str(v["outdir"]), float(v["thr"]), None, bool(v["prefill"]), float(v["kd"]), write_network=True,
                              **self._advanced(v))
        res = pipeline.run(par, log=messages.addMessage)
        if v["runout"]:
            rp = part2.RunoutParams(float(v["mina"]), float(v["maxa"]), float(v["spla"]), float(v["fac"]), float(v["rst"]),
                                    main_branch=str(v["branch"] or "area"), extend_downstream_m=float(v["ext"] or 0), whole_network=bool(v["wnet"]))
            part2.analyse(res, rp, str(v["outdir"]), log=messages.addMessage)
        messages.addMessage("DFCC completed: %s" % v["outdir"])
