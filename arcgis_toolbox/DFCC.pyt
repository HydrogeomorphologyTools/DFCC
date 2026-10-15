# -*- coding: utf-8 -*-
"""ArcGIS Pro Python toolbox for DFCC (Python 3 only; ArcMap 10.x runs Python 2.7 -> use the GUI/CLI instead).

Requires the package:  pip install dfcc   (in the ArcGIS Pro python environment, e.g. a cloned env),
or keep this folder next to ../src of the source checkout."""
import os
import sys
import arcpy


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
        p[-2].filter.type = "ValueList"
        p[-3].filter.list = ["area", "longest", "highest"]
        for prm, v in zip(p[2:], [50.0, False, 50.0, True, 1.0, 20.0, 2.0, 0.4, 30.0, "area", 0.0, False]):
            prm.value = v
        return p

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
        if v["runout"]:
            cmd += ["--runout", "--min-area", str(v["mina"]), "--max-area", str(v["maxa"]), "--split-area", str(v["spla"]),
                    "--energy-factor", str(v["fac"]), "--min-restart-len", str(v["rst"]),
                    "--main-branch", str(v["branch"] or "area"), "--extend-downstream", str(v["ext"] or 0)] + (["--whole-network"] if v["wnet"] else [])
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
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
        par = pipeline.Params(dtm, str(v["outdir"]), float(v["thr"]), None, bool(v["prefill"]), float(v["kd"]), write_network=True)
        res = pipeline.run(par, log=messages.addMessage)
        if v["runout"]:
            rp = part2.RunoutParams(float(v["mina"]), float(v["maxa"]), float(v["spla"]), float(v["fac"]), float(v["rst"]),
                                    main_branch=str(v["branch"] or "area"), extend_downstream_m=float(v["ext"] or 0), whole_network=bool(v["wnet"]))
            part2.analyse(res, rp, str(v["outdir"]), log=messages.addMessage)
        messages.addMessage("DFCC completed: %s" % v["outdir"])
