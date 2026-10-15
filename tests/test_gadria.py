"""Bit-level comparison with the original ArcGIS/TauDEM outputs on the Gadria 2.5 m test.

The DTM is examples/gadria/gadria_dtm_2.5m.tif; the original ArcGIS/TauDEM outputs (RetClassDF.tif, DensitaDF.tif,
Reticolo3D.shp) are in examples/gadria/reference. Override the reference folder with DFCC_TEST_DATA."""
import os
from pathlib import Path
import numpy as np
import pytest
import rasterio
import shapefile
from dfcc import pipeline

EX = Path(__file__).resolve().parents[1] / "examples" / "gadria"
DATA = Path(os.environ.get("DFCC_TEST_DATA", EX / "reference"))
DTM = EX / "gadria_dtm_2.5m.tif"
pytestmark = pytest.mark.skipif(not (DTM.exists() and (DATA / "RetClassDF.tif").exists()), reason="Gadria reference data not available")


@pytest.fixture(scope="module")
def res(tmp_path_factory):
    out = tmp_path_factory.mktemp("gadria")
    return pipeline.run(pipeline.Params(str(DTM), str(out), threshold=50, resolution=2.5), log=lambda *a: None)


def test_class_raster(res):
    ref = rasterio.open(DATA / "RetClassDF.tif").read(1).astype("int64")
    ref = np.where(ref == 4294967295, 0, ref)
    assert (res.retclass != ref).sum() == 0


def test_density(res):
    r = rasterio.open(DATA / "DensitaDF.tif")
    ref = r.read(1)
    v = ref != r.nodata
    assert (res.density[v] != ref[v]).sum() == 0


def test_network_geometry(res):
    sh = shapefile.Reader(str(DATA / "Reticolo3D")).shapes()
    key = lambda xy: tuple(np.round(np.asarray(xy)[[0, -1]].ravel(), 3))
    mine = {key(a["xyz"][:, :2]): a for a in res.arcs}
    assert len(sh) == len(res.arcs)
    for s in sh:
        a = mine[key(s.points)]
        assert len(a["xyz"]) == len(s.points)
        assert np.abs(a["xyz"][:, :2] - np.array(s.points)).max() < 1e-6
        assert np.abs(a["xyz"][:, 2] - np.array(s.z)).max() < 1e-4
