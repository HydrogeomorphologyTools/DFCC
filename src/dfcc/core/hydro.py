"""TauDEM-equivalent hydrology primitives used by DFCC (numba accelerated).

Every routine reproduces the corresponding TauDEM 5.3 tool bit-for-bit:
PitRemove, DinfFlowDir, D8FlowDir, AreaD8 (-nc), SlopeArea, D8FlowPathExtremeUp (-nc),
Threshold.  D8 codes follow TauDEM: 1=E 2=NE 3=N 4=NW 5=W 6=SW 7=S 8=SE.
"""
from __future__ import annotations
import numpy as np
from ._jit import njit
from .native.d8flowdir import compute_d8_flowdir
from .native.dinfflowdir import compute_dinf_flowdir

# TauDEM d1 (col offset) / d2 (row offset), index 1..8
D1 = np.array([0, 1, 1, 0, -1, -1, -1, 0, 1], dtype=np.int64)
D2 = np.array([0, 0, -1, -1, -1, 0, 1, 1, 1], dtype=np.int64)
MISSING_F32 = np.float32(-3.4028234663852886e+38)


# ----------------------------------------------------------------- pit fill
@njit
def _heap_push(hk, hi, n, key, idx):
    i = n
    hk[i] = key
    hi[i] = idx
    while i > 0:
        par = (i - 1) >> 1
        if hk[par] > hk[i]:
            tk = hk[par]; hk[par] = hk[i]; hk[i] = tk
            ti = hi[par]; hi[par] = hi[i]; hi[i] = ti
            i = par
        else:
            break
    return n + 1


@njit
def _heap_pop(hk, hi, n):
    key = hk[0]
    idx = hi[0]
    n -= 1
    hk[0] = hk[n]
    hi[0] = hi[n]
    i = 0
    while True:
        l = 2 * i + 1
        r = l + 1
        s = i
        if l < n and hk[l] < hk[s]:
            s = l
        if r < n and hk[r] < hk[s]:
            s = r
        if s == i:
            break
        tk = hk[s]; hk[s] = hk[i]; hk[i] = tk
        ti = hi[s]; hi[s] = hi[i]; hi[i] = ti
        i = s
    return key, idx, n


@njit
def _priority_flood(dem, valid, edge_drains_nodata):
    """Wang & Liu / Barnes priority-flood, 8-neighbours, no epsilon.
    Seeds: valid cells on the grid border (and, if edge_drains_nodata, cells touching NoData)."""
    ny, nx = dem.shape
    out = dem.copy()
    closed = np.zeros((ny, nx), np.uint8)
    N = ny * nx
    hk = np.empty(N, np.float32)
    hi = np.empty(N, np.int64)
    pit = np.empty(N, np.int64)
    ph = 0
    pt = 0
    n = 0
    for r in range(ny):
        for c in range(nx):
            if not valid[r, c]:
                continue
            seed = r == 0 or c == 0 or r == ny - 1 or c == nx - 1
            if not seed and edge_drains_nodata:
                for k in range(1, 9):
                    rr = r + D2[k]
                    cc = c + D1[k]
                    if not valid[rr, cc]:
                        seed = True
                        break
            if seed:
                closed[r, c] = 1
                n = _heap_push(hk, hi, n, out[r, c], r * nx + c)
    while n > 0 or ph < pt:
        if ph < pt:
            cur = pit[ph]
            ph += 1
            z = out[cur // nx, cur % nx]
        else:
            z, cur, n = _heap_pop(hk, hi, n)
        r = cur // nx
        c = cur % nx
        for k in range(1, 9):
            rr = r + D2[k]
            cc = c + D1[k]
            if rr < 0 or cc < 0 or rr >= ny or cc >= nx:
                continue
            if closed[rr, cc] or not valid[rr, cc]:
                continue
            closed[rr, cc] = 1
            if out[rr, cc] <= z:
                out[rr, cc] = z
                pit[pt] = rr * nx + cc
                pt += 1
            else:
                n = _heap_push(hk, hi, n, out[rr, cc], rr * nx + cc)
    return out


def valid_mask(a, nodata):
    m = np.isfinite(a)
    if nodata is not None:
        if np.isnan(nodata):
            return m
        m &= a != np.asarray(nodata, dtype=a.dtype)
    return m


def fill_depressions(dem, nodata, edge_drains_nodata=True):
    """TauDEM PitRemove equivalent (identical elevations to the reference tool).
    Returns float32 array (NoData cells keep their original value)."""
    dem = np.ascontiguousarray(dem, dtype=np.float32)
    valid = valid_mask(dem, nodata)
    # numba needs a padded index-safe valid mask for neighbour tests
    vp = np.zeros((dem.shape[0] + 2, dem.shape[1] + 2), bool)
    vp[1:-1, 1:-1] = valid
    return _priority_flood_pad(dem, valid, bool(edge_drains_nodata))


def _priority_flood_pad(dem, valid, edge):
    ny, nx = dem.shape
    # guard: neighbour test in seed loop needs in-bounds access -> run on padded copies
    d = np.zeros((ny + 2, nx + 2), np.float32)
    v = np.zeros((ny + 2, nx + 2), np.bool_)
    d[1:-1, 1:-1] = dem
    v[1:-1, 1:-1] = valid
    out = _priority_flood(d, v, edge)
    # padded frame is NoData, so border cells touch NoData; emulate "grid border" seeding
    return out[1:-1, 1:-1].copy()


# ------------------------------------------------------------- flow directions
def d8_flowdir(fel, nodata, cell):
    """Returns (p int16 [-32768 nodata, 1..8, 0 unresolved], sd8 float32 [-1 nodata])."""
    p, sd8 = compute_d8_flowdir(fel, float(cell), nodata, log_func=lambda *a: None)
    p_i = np.where(p < 0, -32768, p).astype(np.int16)
    sd8 = np.asarray(sd8, np.float32).copy()
    sd8[p_i == -32768] = -1.0
    return p_i, sd8


def dinf_slope(fel, nodata, cell):
    """Returns (ang float32 [-1 nodata], slp float32 [-1 nodata]) like TauDEM DinfFlowDir."""
    ang, slp = compute_dinf_flowdir(fel, float(cell), nodata, log_func=lambda *a: None)
    ang = np.asarray(ang, np.float32).copy()
    slp = np.asarray(slp, np.float32).copy()
    bad = ang < -1e30
    ang[bad] = -1.0
    slp[bad] = -1.0
    return ang, slp


# ------------------------------------------------------------ D8 accumulations
@njit
def _indegree(p):
    ny, nx = p.shape
    deg = np.zeros((ny, nx), np.int32)
    for r in range(ny):
        for c in range(nx):
            k = p[r, c]
            if k >= 1 and k <= 8:
                rr = r + D2[k]
                cc = c + D1[k]
                if rr >= 0 and cc >= 0 and rr < ny and cc < nx and p[rr, cc] != -32768:
                    deg[rr, cc] += 1
    return deg


@njit
def _area_d8(p, deg):
    ny, nx = p.shape
    area = np.ones((ny, nx), np.float64)
    q = np.empty(ny * nx, np.int64)
    qt = 0
    for r in range(ny):
        for c in range(nx):
            if p[r, c] != -32768 and deg[r, c] == 0:
                q[qt] = r * nx + c
                qt += 1
    qh = 0
    while qh < qt:
        cur = q[qh]
        qh += 1
        r = cur // nx
        c = cur % nx
        k = p[r, c]
        if k >= 1 and k <= 8:
            rr = r + D2[k]
            cc = c + D1[k]
            if rr >= 0 and cc >= 0 and rr < ny and cc < nx and p[rr, cc] != -32768:
                area[rr, cc] += area[r, c]
                deg[rr, cc] -= 1
                if deg[rr, cc] == 0:
                    q[qt] = rr * nx + cc
                    qt += 1
    return area


def area_d8(p):
    """D8 contributing area in cells (TauDEM AreaD8 -nc). float32, nodata -1."""
    p = np.ascontiguousarray(p, dtype=np.int16)
    deg = _indegree(p)
    a = _area_d8(p, deg).astype(np.float32)
    a[p == -32768] = -1.0
    return a


@njit
def _extreme_up(p, sa, deg):
    ny, nx = p.shape
    ssa = sa.copy()
    q = np.empty(ny * nx, np.int64)
    qt = 0
    for r in range(ny):
        for c in range(nx):
            if p[r, c] != -32768 and deg[r, c] == 0:
                q[qt] = r * nx + c
                qt += 1
    qh = 0
    while qh < qt:
        cur = q[qh]
        qh += 1
        r = cur // nx
        c = cur % nx
        k = p[r, c]
        if k >= 1 and k <= 8:
            rr = r + D2[k]
            cc = c + D1[k]
            if rr >= 0 and cc >= 0 and rr < ny and cc < nx and p[rr, cc] != -32768:
                if ssa[r, c] > ssa[rr, cc]:
                    ssa[rr, cc] = ssa[r, c]
                deg[rr, cc] -= 1
                if deg[rr, cc] == 0:
                    q[qt] = rr * nx + cc
                    qt += 1
    return ssa


def slope_area(slope, area, m=1.0, n=0.5):
    """TauDEM SlopeArea: S^m * A^n evaluated in float32 (as in the C++ tool). NoData = -1."""
    ok = (slope >= 0) & (area >= 0)
    sa = np.full(slope.shape, -1.0, np.float32)
    f = np.float32
    sa[ok] = np.power(slope[ok].astype(f), f(m)) * np.power(area[ok].astype(f), f(n))
    return sa


def max_upslope(p, sa):
    """TauDEM D8FlowPathExtremeUp (max, no edge-contamination check)."""
    p = np.ascontiguousarray(p, dtype=np.int16)
    deg = _indegree(p)
    ssa = _extreme_up(p, np.ascontiguousarray(sa, np.float32), deg)
    ssa[p == -32768] = MISSING_F32
    return ssa


def threshold_stream(ssa, thresh):
    """TauDEM Threshold: 1 where ssa >= thresh, 0 otherwise, -32768 nodata."""
    src = np.where(ssa >= np.float32(thresh), 1, 0).astype(np.int16)
    src[ssa < -1e30] = -32768
    return src
