"""Fill must be identical to ArcGIS Spatial Analyst Fill (reference produced with ArcMap 10.8)."""
from pathlib import Path
import numpy as np
import rasterio
from dfcc.core import hydro

D = Path(__file__).parent / "data"


def test_fill_equals_arcgis():
    with rasterio.open(D / "dem_sint.tif") as s:
        dem, nd = s.read(1), s.nodata
    with rasterio.open(D / "dem_sint_fill_arcgis.tif") as a:
        ref, rnd = a.read(1), a.nodata
    valid = dem != nd
    assert ((ref == rnd) == ~valid).all()
    out = hydro.fill_depressions(dem, nd)
    assert (out[valid] != ref[valid]).sum() == 0
    assert (ref[valid] != dem[valid]).sum() > 1000          # the test DEM really needs filling
