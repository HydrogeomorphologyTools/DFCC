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

S_MAX = np.float32(0.7812)      # Con(slp < 0.7812, slp)
S_DEP_MAX = np.float32(0.1405)  # upper slope limit of deposition / slowing
S_STOP = np.float32(0.0524)     # stop: slope < 0.0524 (3 deg)
WB_K = np.float32(0.32)
WB_EXP = np.float32(-0.2)
AREA_MAX_KM2 = np.float32(20.0)


@njit
def _classify(src, slp, ad8, res, out_class, out_indf):
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
            valid_s = (s >= 0) and (s < S_MAX)          # s38 not NoData
            a = ad8[r, c]
            akm2 = f32(f32(a * res) * res) / f32(1000000.0)
            ret = 1 if sv == 1 else 0
            tot = ret
            indf = 0
            if valid_s:
                wb = f32(WB_K * f32(np.power(akm2, WB_EXP)))
                if s > wb and akm2 < AREA_MAX_KM2:
                    indf = 1
                    if ret == 1:
                        tot += 1                               # initiation
                dep1 = (s < S_DEP_MAX) and (s > S_STOP)
                in8 = (s > wb) and (s < S_DEP_MAX)
                dd = (1 if dep1 else 0) - (1 if in8 else 0)
                if ret == 1 and dd != 0:
                    tot += 2                                   # slowing
                if ret == 1 and s < S_STOP:
                    tot += 3                                   # stop
            out_indf[r, c] = indf
            out_class[r, c] = tot if tot > 0 else 0


def classify_network(src, slp, ad8, cell):
    """Return (class raster uint8 [0 = NoData], inDF uint8 [1 = initiation-prone cell])."""
    cls = np.zeros(src.shape, np.uint8)
    indf = np.zeros(src.shape, np.uint8)
    _classify(np.ascontiguousarray(src, np.int16), np.ascontiguousarray(slp, np.float32),
              np.ascontiguousarray(ad8, np.float32), np.float32(cell), cls, indf)
    return cls, indf
