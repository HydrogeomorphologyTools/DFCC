"""DTM generalization: resample the DTM to a coarser cell size before the procedure.

The default thresholds of Procedura DF come from literature based on ~10 m, non-LiDAR DTMs: slopes are meant to be
reach-scale slopes, not the very local slopes of a boulder step or a check dam that a high-resolution LiDAR DTM resolves.
Aggregating a fine DTM to a coarser grid restores that representativeness.

The output grid keeps the upper-left corner of the input; the last partial row / column is dropped.
NoData cells are ignored; an output cell is NoData only when it has no valid input cell.

* `average` and `median` are computed here (numba), independently of GDAL and of the CRS, so they give the same result
  with every back-end (rasterio wheels, QGIS / OSGeo4W GDAL, ArcGIS Pro GDAL).
  average = mean of the input cells weighted by their overlap with the output cell (exact area-weighted aggregation);
  median  = median of the input cells whose centre falls inside the output cell.
* `bilinear` and `cubic` are GDAL interpolators (rasterio.warp.reproject, or osgeo.gdal.Warp).
"""
from __future__ import annotations
import math
import numpy as np

from .. import io as dio
from ._jit import njit

# name -> (GDAL resampling name or None when computed here, short description for CLI / GUI)
METHODS = {
    "average": (None, "mean of the input cells (recommended)"),
    "median": (None, "median of the input cells: robust to spikes, boulders, artefacts"),
    "bilinear": ("bilinear", "bilinear interpolation (smooth)"),
    "cubic": ("cubic", "cubic convolution (smooth, can slightly overshoot)"),
}
DEFAULT_METHOD = "average"


def output_shape(shape, cell, target_cell):
    ny, nx = shape
    return max(1, int(math.floor(ny * cell / target_cell + 1e-9))), max(1, int(math.floor(nx * cell / target_cell + 1e-9)))


@njit
def _overlap(i, r, n):
    """Input index range [j0, j1) and overlap weights of output cell i (size r input cells) along one axis."""
    a, b = i * r, (i + 1) * r
    j0 = int(math.floor(a + 1e-9))
    j1 = min(n, int(math.ceil(b - 1e-9)))
    w = np.empty(max(0, j1 - j0), np.float64)
    for j in range(j0, j1):
        w[j - j0] = min(b, j + 1.0) - max(a, float(j))
    return j0, j1, w


@njit
def _aggregate(z, valid, r, ny, nx, median, nd):
    out = np.full((ny, nx), nd, np.float32)
    buf = np.empty(int(math.ceil(r) + 1) ** 2, np.float64)
    for i in range(ny):
        y0, y1, wy = _overlap(i, r, z.shape[0])
        for k in range(nx):
            x0, x1, wx = _overlap(k, r, z.shape[1])
            if median:
                m = 0
                for y in range(y0, y1):
                    if not (i * r <= y + 0.5 < (i + 1) * r):
                        continue
                    for x in range(x0, x1):
                        if valid[y, x] and (k * r <= x + 0.5 < (k + 1) * r):
                            buf[m] = z[y, x]
                            m += 1
                if m > 0:
                    out[i, k] = np.median(buf[:m])
            else:
                s = 0.0
                sw = 0.0
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        if valid[y, x]:
                            w = wy[y - y0] * wx[x - x0]
                            s += w * z[y, x]
                            sw += w
                if sw > 0:
                    out[i, k] = s / sw
    return out


def _gdal_interpolate(src, nd, g, target_cell, shape, method):
    ny, nx = shape
    dst = np.full((ny, nx), nd, np.float32)
    if dio.BACKEND == "rasterio":
        from rasterio.warp import reproject, Resampling
        from rasterio.transform import Affine
        from rasterio.crs import CRS
        crs = CRS.from_wkt(g.wkt) if g.wkt else CRS.from_epsg(3857)     # same CRS in and out: no reprojection happens
        reproject(src, dst, src_transform=Affine(g.cell, 0, g.x0, 0, -g.cell, g.y0), src_crs=crs, src_nodata=nd,
                  dst_transform=Affine(target_cell, 0, g.x0, 0, -target_cell, g.y0), dst_crs=crs, dst_nodata=nd,
                  resampling=getattr(Resampling, method))
    elif dio.BACKEND == "gdal":
        from osgeo import gdal
        drv = gdal.GetDriverByName("MEM")
        s = drv.Create("", src.shape[1], src.shape[0], 1, gdal.GDT_Float32)
        s.SetGeoTransform((g.x0, g.cell, 0, g.y0, 0, -g.cell))      # no SRS: in == out, nothing to reproject
        s.GetRasterBand(1).WriteArray(src)
        s.GetRasterBand(1).SetNoDataValue(nd)
        d = gdal.Warp("", s, format="MEM", outputBounds=(g.x0, g.y0 - ny * target_cell, g.x0 + nx * target_cell, g.y0),
                      width=nx, height=ny, resampleAlg=method, srcNodata=nd, dstNodata=nd)
        dst = d.GetRasterBand(1).ReadAsArray().astype(np.float32)
    else:
        raise RuntimeError("Neither rasterio nor GDAL (osgeo) is available")
    return dst


def generalize(g: dio.Grid, target_cell: float, method: str = DEFAULT_METHOD, nodata: float = -9999.0) -> dio.Grid:
    """Return a new float32 Grid with cell size `target_cell` (must be coarser than the input)."""
    if method not in METHODS:
        raise ValueError(f"unknown generalization method '{method}' (choose among {', '.join(METHODS)})")
    if not target_cell or target_cell <= g.cell * (1 + 1e-9):
        raise ValueError(f"generalization cell size ({target_cell}) must be larger than the DTM cell size ({g.cell})")
    nd = float(g.nodata) if g.nodata is not None and not math.isnan(float(g.nodata)) else float(nodata)
    src = np.ascontiguousarray(g.data, dtype=np.float32)
    valid = np.isfinite(src) & (src != np.float32(nd))
    src = np.where(valid, src, np.float32(nd)).astype(np.float32)
    shape = output_shape(src.shape, g.cell, target_cell)
    gdal_name = METHODS[method][0]
    if gdal_name is None:
        dst = _aggregate(src, valid, float(target_cell) / float(g.cell), shape[0], shape[1], method == "median", np.float32(nd))
    else:
        dst = _gdal_interpolate(src, nd, g, float(target_cell), shape, gdal_name)
        if valid.any() and not np.any(dst != np.float32(nd)):
            raise RuntimeError(f"the GDAL library in use returned an empty raster for '{method}' resampling; "
                               f"use the 'average' or 'median' method (computed by DFCC itself)")
    return dio.Grid(dst, g.x0, g.y0, float(target_cell), nd, g.wkt, float(target_cell))
