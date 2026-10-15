"""Save / load the full set of DFCC parameters as JSON (shared by CLI, GUI and plug-ins)."""
from __future__ import annotations
import json
from dataclasses import asdict, fields
from pathlib import Path
from . import __version__
from .pipeline import Params
from .part2 import RunoutParams


def to_dict(par: Params, rp: RunoutParams | None = None, run_runout: bool = False) -> dict:
    return {"dfcc_version": __version__, "procedure": asdict(par),
            "runout": {"enabled": bool(run_runout), **(asdict(rp) if rp else asdict(RunoutParams()))}}


def save(path, par: Params, rp: RunoutParams | None = None, run_runout: bool = False):
    Path(path).write_text(json.dumps(to_dict(par, rp, run_runout), indent=2, ensure_ascii=False), encoding="utf-8")


def _build(cls, d):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})


def load(path):
    """Returns (Params, RunoutParams, run_runout)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    pr = d.get("procedure", {})
    ru = dict(d.get("runout", {}))
    enabled = bool(ru.pop("enabled", False))
    pp = ru.get("pour_points")
    if pp:
        ru["pour_points"] = [tuple(p) for p in pp]
    return _build(Params, pr), _build(RunoutParams, ru), enabled
