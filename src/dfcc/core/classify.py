"""DFCC channel-network classification (replicates the ArcGIS ModelBuilder map algebra).

Classes (ClassifiedNetwork): 1 propagation, 2 initiation, 3 slowing-down, 4 stop.
Thresholds: slope-area criteria of the original Procedura DF (Crema & Cavalli).
"""
from __future__ import annotations
import numpy as np
from ._jit import njit

PROPAGATION, INITIATION, SLOWING, STOP = 1, 2, 3, 4
CLASS_NAMES = {1: "propagation", 2: "initiation", 3: "slowing", 4: "stop"}
CLASS_COLORS = {1: "#1f5fbf", 2: "#d62828", 3: "#f77f00", 4: "#2a9d3c"}

# Defaults of the original Procedura DF; all of them can be overridden through pipeline.Params
S_MAX = 0.7812          # Con(slp < 0.7812, slp): steeper cells are ignored (38 deg)
S_DEP_MAX = 0.1405      # upper slope limit of deposition / slowing (8 deg)
S_STOP = 0.0524         # stop: slope < 0.0524 (3 deg)
WB_K = 0.32             # initiation: s > WB_K * A^WB_EXP (A in km2)
WB_EXP = -0.2
AREA_MAX_KM2 = 20.0     # initiation only where A < AREA_MAX_KM2


@njit
def _classify(src, slp, ad8, res, s_max, s_dep_max, s_stop, wb_k, wb_exp, area_max, out_class, out_indf):
    ny, nx = src.shape
    f32 = np.float32
    for r in range(ny):
        for c in range(nx):
            sv = src[r, c]
            if sv == -32768:
                out_class[r, c] = 0
                out_indf[r, c] = 0
                continue
            s = slp[r, c]
            valid_s = (s >= 0) and (s < s_max)          # s38 not NoData
            a = ad8[r, c]
            akm2 = f32(f32(a * res) * res) / f32(1000000.0)
            ret = 1 if sv == 1 else 0
            tot = ret
            indf = 0
            if valid_s:
                wb = f32(wb_k * f32(np.power(akm2, wb_exp)))
                if s > wb and akm2 < area_max:
                    indf = 1
                    if ret == 1:
                        tot += 1                               # initiation
                dep1 = (s < s_dep_max) and (s > s_stop)
                in8 = (s > wb) and (s < s_dep_max)
                dd = (1 if dep1 else 0) - (1 if in8 else 0)
                if ret == 1 and dd != 0:
                    tot += 2                                   # slowing
                if ret == 1 and s < s_stop:
                    tot += 3                                   # stop
            out_indf[r, c] = indf
            out_class[r, c] = tot if tot > 0 else 0


def check_thresholds(s_max=S_MAX, s_dep_max=S_DEP_MAX, s_stop=S_STOP, wb_k=WB_K, area_max_km2=AREA_MAX_KM2):
    """Raise ValueError unless 0 < stop < slowing upper limit < max slope, with positive initiation coefficient and area."""
    if not 0 < s_stop < s_dep_max < s_max:
        raise ValueError(f"slope thresholds must satisfy 0 < stop ({s_stop}) < slowing upper limit ({s_dep_max}) "
                         f"< max slope ({s_max})")
    if wb_k <= 0 or area_max_km2 <= 0:
        raise ValueError("the initiation coefficient and the maximum initiation area must be positive")


def classify_network(src, slp, ad8, cell, s_max=S_MAX, s_dep_max=S_DEP_MAX, s_stop=S_STOP,
                     wb_k=WB_K, wb_exp=WB_EXP, area_max_km2=AREA_MAX_KM2):
    """Return (class raster uint8 [0 = NoData], inDF uint8 [1 = initiation-prone cell])."""
    check_thresholds(s_max, s_dep_max, s_stop, wb_k, area_max_km2)
    cls = np.zeros(src.shape, np.uint8)
    indf = np.zeros(src.shape, np.uint8)
    f32 = np.float32
    _classify(np.ascontiguousarray(src, np.int16), np.ascontiguousarray(slp, np.float32),
              np.ascontiguousarray(ad8, np.float32), f32(cell), f32(s_max), f32(s_dep_max), f32(s_stop),
              f32(wb_k), f32(wb_exp), f32(area_max_km2), cls, indf)
    return cls, indf
