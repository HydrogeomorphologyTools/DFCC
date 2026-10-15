"""Compile (or load from cache) every numba kernel on a small synthetic DTM, in the *calling* thread.

Why: on Windows, compiling numba kernels inside a worker thread (the GUI's QThread) can crash the frozen executable
with an access violation (C-stack exhaustion in the compiler). Calling `warmup()` from the main thread first guarantees
that the worker only runs already-compiled code."""
from __future__ import annotations
import tempfile
from pathlib import Path
import numpy as np

_done = False


def synthetic_dtm(n=240, cell=5.0, seed=3):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:n, 0:n].astype(np.float32)
    z = 1500 + 3.2 * (n - y) + 40 * np.sin(x / 17.0) + 25 * np.cos((x + y) / 23.0)     # sloping valley with relief
    z += 30 * np.exp(-((x - n / 2) ** 2) / (2 * 18.0 ** 2)) * -1                        # a central gully
    k = rng.normal(0, 1.2, z.shape).astype(np.float32)
    z = (z + k).astype(np.float32)
    z[:3, :] = -9999.0                                                                  # some NoData border
    z[:, :2] = -9999.0
    return z, cell


def warmup(log=None):
    global _done
    if _done:
        return
    from . import io as dio, pipeline, part2
    z, cell = synthetic_dtm()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        from .io import Grid
        g = Grid(z, 600000.0, 5100000.0 + z.shape[0] * cell, cell, -9999.0, "")
        dio.write_raster(str(td / "w.tif"), g, z, -9999.0, "float32")
        for prefill in (False, True):
            res = pipeline.run(pipeline.Params(str(td / "w.tif"), str(td / "o"), threshold=5, prefill=prefill,
                                               write_network=True, write_high_density=True), log=lambda *a: None)
        for br in ("area", "longest", "highest"):
            part2.analyse(res, part2.RunoutParams(min_area_km2=0.0, max_area_km2=1e3, main_branch=br, extend_downstream_m=100.0),
                          str(td / "o"), log=lambda *a: None)
        from .core import resample                     # DTM generalization kernels (average, median)
        for m in ("average", "median"):
            resample.generalize(g, cell * 2.5, m)
    _done = True
