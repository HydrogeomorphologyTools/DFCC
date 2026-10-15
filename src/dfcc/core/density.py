"""Kernel density of initiation cells (ArcGIS Spatial Analyst KernelDensity equivalent)
and natural-breaks (Jenks) extraction of high-density areas."""
from __future__ import annotations
import math
import numpy as np
from ._jit import njit


@njit
def _kd(pts, res, radius, nr, out):
    ny, nx = pts.shape
    r2 = radius * radius
    k3 = 3.0 / math.pi
    for r in range(ny):
        for c in range(nx):
            if pts[r, c] == 0:
                continue
            for dr in range(-nr, nr + 1):
                rr = r + dr
                if rr < 0 or rr >= ny:
                    continue
                for dc in range(-nr, nr + 1):
                    cc = c + dc
                    if cc < 0 or cc >= nx:
                        continue
                    d2 = (dr * dr + dc * dc) * res * res
                    if d2 < r2:
                        u = 1.0 - d2 / r2
                        out[rr, cc] += k3 * u * u


def kernel_density(points, cell, radius=50.0, area_unit_m2=10000.0, valid=None):
    """Quartic (Silverman) kernel density of unit-weight points located at cell centres.

    Identical to ArcGIS KernelDensity(population=NONE, radius, HECTARES, DENSITIES, PLANAR):
    density = area_unit/radius^2 * sum 3/pi (1-(d/r)^2)^2, d < radius.   [points per hectare]
    """
    pts = np.ascontiguousarray(points != 0, dtype=np.uint8)
    out = np.zeros(pts.shape, np.float64)
    nr = int(radius // cell) + 1
    _kd(pts, float(cell), float(radius), nr, out)
    out *= area_unit_m2 / (radius * radius)
    out = out.astype(np.float32)
    if valid is not None:
        out[~valid] = np.float32(-3.4028234663852886e+38)
    return out


def jenks2(values):
    """Exact optimal 2-class natural breaks (Fisher-Jenks) of a 1-D sample.
    Returns (upper_bound_of_class1, lower_bound_of_class2)."""
    v = np.sort(np.asarray(values, dtype=np.float64).ravel())
    n = v.size
    if n < 2:
        raise ValueError("not enough values for natural breaks")
    cs = np.cumsum(v)
    cs2 = np.cumsum(v * v)
    i = np.arange(1, n)                       # class 1 = v[:i]
    sse1 = cs2[:-1] - cs[:-1] ** 2 / i
    sse2 = (cs2[-1] - cs2[:-1]) - (cs[-1] - cs[:-1]) ** 2 / (n - i)
    tot = sse1 + sse2
    # ties: split must fall between distinct values
    distinct = v[1:] != v[:-1]
    tot = np.where(distinct, tot, np.inf)
    k = int(np.argmin(tot))
    return float(v[k]), float(v[k + 1])


def high_density_mask(density, valid=None):
    """Exclude zeros, 2-class natural breaks on the rest; return (mask_high, break_value)."""
    d = density
    ok = (d > 0) if valid is None else ((d > 0) & valid)
    b1, b2 = jenks2(d[ok])
    return ok & (d >= b2), b1
