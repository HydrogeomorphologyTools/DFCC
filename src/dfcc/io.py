"""Raster / vector I/O with interchangeable back-ends (rasterio or GDAL/osgeo, pyshp for vectors)."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np

try:
    import rasterio
    from rasterio.crs import CRS as _CRS
    BACKEND = "rasterio"
except Exception:  # pragma: no cover
    rasterio = None
    try:
        from osgeo import gdal, osr
        gdal.UseExceptions()
        BACKEND = "gdal"
    except Exception:
        BACKEND = None


@dataclass
class Grid:
    """Raster values plus georeferencing."""
    data: np.ndarray
    x0: float                  # west edge
    y0: float                  # north edge
    cell: float                # (square) cell size
    nodata: float | None
    wkt: str = ""
    cell_y: float | None = None
    meta: dict = field(default_factory=dict)

    @property
    def shape(self):
        return self.data.shape

    @property
    def transform(self):
        return (self.x0, self.y0)

    def like(self, data, nodata=None):
        return Grid(data, self.x0, self.y0, self.cell, nodata, self.wkt, self.cell_y)

    def xy(self, row, col):
        return self.x0 + (np.asarray(col) + 0.5) * self.cell, self.y0 - (np.asarray(row) + 0.5) * self.cell

    def rowcol(self, x, y):
        return (np.floor((self.y0 - np.asarray(y)) / self.cell).astype(int),
                np.floor((np.asarray(x) - self.x0) / self.cell).astype(int))


def read_raster(path) -> Grid:
    path = str(path)
    if BACKEND == "rasterio":
        with rasterio.open(path) as r:
            a = r.read(1)
            t = r.transform
            wkt = r.crs.to_wkt() if r.crs else ""
            g = Grid(a, t.c, t.f, abs(t.a), r.nodata, wkt, abs(t.e))
    elif BACKEND == "gdal":
        ds = gdal.Open(path)
        b = ds.GetRasterBand(1)
        gt = ds.GetGeoTransform()
        g = Grid(b.ReadAsArray(), gt[0], gt[3], abs(gt[1]), b.GetNoDataValue(), ds.GetProjection(), abs(gt[5]))
    else:
        raise RuntimeError("Neither rasterio nor GDAL (osgeo) is available")
    if g.cell_y is not None and abs(g.cell - g.cell_y) > 1e-9 * g.cell:
        raise ValueError(f"Non-square cells ({g.cell} x {g.cell_y}); resample the DTM first")
    return g


def write_raster(path, grid: Grid, data=None, nodata=None, dtype=None, compress=True):
    path = str(path)
    a = grid.data if data is None else data
    if dtype is not None:
        a = a.astype(dtype)
    if BACKEND == "rasterio":
        prof = dict(driver="GTiff", height=a.shape[0], width=a.shape[1], count=1, dtype=a.dtype,
                    transform=rasterio.Affine(grid.cell, 0, grid.x0, 0, -grid.cell, grid.y0), nodata=nodata,
                    tiled=True, blockxsize=256, blockysize=256)
        if compress:
            prof["compress"] = "lzw"
        if grid.wkt:
            prof["crs"] = _CRS.from_wkt(grid.wkt)
        if a.size > 2 ** 28:
            prof["BIGTIFF"] = "YES"
        with rasterio.open(path, "w", **prof) as w:
            w.write(a, 1)
    else:
        from osgeo import gdal_array
        gt = (grid.x0, grid.cell, 0, grid.y0, 0, -grid.cell)
        drv = gdal.GetDriverByName("GTiff")
        opts = ["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"] if compress else []
        ds = drv.Create(path, a.shape[1], a.shape[0], 1, gdal_array.NumericTypeCodeToGDALTypeCode(a.dtype.type), opts)
        ds.SetGeoTransform(gt)
        if grid.wkt:
            ds.SetProjection(grid.wkt)
        b = ds.GetRasterBand(1)
        if nodata is not None:
            b.SetNoDataValue(float(nodata))
        b.WriteArray(a)
        ds.FlushCache()
        ds = None


# ------------------------------------------------------------------ vectors
def _esri_wkt(wkt: str) -> str:
    if not wkt:
        return ""
    try:
        if BACKEND == "rasterio":
            return _CRS.from_wkt(wkt).to_wkt(version="WKT1_ESRI")
        sr = osr.SpatialReference()
        sr.ImportFromWkt(wkt)
        sr.MorphToESRI()
        return sr.ExportToWkt()
    except Exception:
        return wkt


def _write_prj(shp_path, wkt):
    w = _esri_wkt(wkt)
    if w:
        Path(shp_path).with_suffix(".prj").write_text(w)


def write_polylines(path, lines, fields, records, wkt="", z=True):
    """lines: list of (N,3) or (N,2) arrays; fields: [(name,'N'|'C'|'F',size,dec)]."""
    import shapefile
    w = shapefile.Writer(str(path), shapeType=shapefile.POLYLINEZ if z else shapefile.POLYLINE)
    w.autoBalance = True
    for f in fields:
        w.field(*f)
    for ln, rec in zip(lines, records):
        ln = np.asarray(ln, float)
        if z:
            w.linez([ln.tolist()])
        else:
            w.line([ln[:, :2].tolist()])
        w.record(*rec)
    w.close()
    _write_prj(path, wkt)


def write_points(path, xy, fields, records, wkt=""):
    import shapefile
    w = shapefile.Writer(str(path), shapeType=shapefile.POINT)
    for f in fields:
        w.field(*f)
    for (x, y), rec in zip(xy, records):
        w.point(float(x), float(y))
        w.record(*rec)
    w.close()
    _write_prj(path, wkt)


def polygonize_mask(mask, grid: Grid, connectivity=4):
    """Vectorise a boolean mask -> list of GeoJSON polygons (dissolved by connectivity)."""
    m = np.ascontiguousarray(mask, dtype=np.uint8)
    out = []
    if BACKEND == "rasterio":
        from rasterio import features
        T = rasterio.Affine(grid.cell, 0, grid.x0, 0, -grid.cell, grid.y0)
        for geom, val in features.shapes(m, mask=m.astype(bool), transform=T, connectivity=8 if connectivity == 8 else 4):
            out.append(geom)
    else:
        mem = gdal.GetDriverByName("MEM").Create("", m.shape[1], m.shape[0], 1, gdal.GDT_Byte)
        mem.SetGeoTransform((grid.x0, grid.cell, 0, grid.y0, 0, -grid.cell))
        b = mem.GetRasterBand(1)
        b.WriteArray(m)
        ogr_ds = __import__("osgeo.ogr", fromlist=["ogr"]).GetDriverByName("Memory").CreateDataSource("x")
        lyr = ogr_ds.CreateLayer("p")
        from osgeo import ogr
        lyr.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
        gdal.Polygonize(b, b, lyr, 0, ["8CONNECTED=%d" % (1 if connectivity == 8 else 0)])
        import json
        for f in lyr:
            out.append(json.loads(f.GetGeometryRef().ExportToJson()))
    return out


def write_polygons(path, geoms, fields, records, wkt=""):
    import shapefile
    w = shapefile.Writer(str(path), shapeType=shapefile.POLYGON)
    for f in fields:
        w.field(*f)
    for g, rec in zip(geoms, records):
        w.shape(g)
        w.record(*rec)
    w.close()
    _write_prj(path, wkt)
