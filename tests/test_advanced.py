"""Advanced parameters (custom thresholds) and DTM generalization."""
import json
import os
from pathlib import Path
import numpy as np
import pytest
from dfcc import pipeline, part2, config, cli, io as dio
from dfcc.core import classify, resample

DEM = Path(__file__).parent / "data" / "dem_sint.tif"
QUIET = dict(log=lambda *a: None)


def _run(tmp_path, name, **kw):
    return pipeline.run(pipeline.Params(str(DEM), str(tmp_path / name), threshold=50, write_network=False,
                                        write_high_density=False, **kw), **QUIET)


def test_explicit_defaults_are_identical(tmp_path):
    a = _run(tmp_path, "a")
    b = _run(tmp_path, "b", s_max=0.7812, s_dep_max=0.1405, s_stop=0.0524, wb_k=0.32, wb_exp=-0.2, area_max_km2=20.0,
             slope_exp=1.0, area_exp=0.5)
    assert np.array_equal(a.retclass, b.retclass) and np.array_equal(a.indf, b.indf)


def test_custom_slope_classes_move_cells(tmp_path):
    base = _run(tmp_path, "base")
    wide = _run(tmp_path, "wide", s_dep_max=0.25, s_stop=0.12)       # more slowing and stop cells
    assert np.array_equal(base.src, wide.src)                         # same network
    assert (wide.retclass == classify.STOP).sum() > (base.retclass == classify.STOP).sum()
    assert (wide.retclass == classify.PROPAGATION).sum() < (base.retclass == classify.PROPAGATION).sum()


def test_custom_initiation_curve(tmp_path):
    base = _run(tmp_path, "base")
    strict = _run(tmp_path, "strict", wb_k=0.6)                       # higher curve -> fewer initiation cells
    assert strict.indf.sum() < base.indf.sum()
    none = _run(tmp_path, "none", area_max_km2=1e-6)                   # no area below the limit -> no initiation
    assert none.indf.sum() == 0


def test_extraction_exponents_change_network(tmp_path):
    base = _run(tmp_path, "base")
    other = _run(tmp_path, "other", area_exp=0.4)
    assert (other.src == 1).sum() < (base.src == 1).sum()


@pytest.mark.parametrize("kw", [dict(s_stop=0.2), dict(s_dep_max=0.9), dict(s_stop=0.0), dict(wb_k=0.0), dict(area_max_km2=-1.0)])
def test_inconsistent_thresholds_are_refused(tmp_path, kw):
    with pytest.raises(ValueError):
        _run(tmp_path, "bad", **kw)
    assert not (tmp_path / "bad").exists()                           # refused before any output is written


@pytest.mark.parametrize("method", list(resample.METHODS))
def test_generalize_grid(method):
    g = dio.read_raster(DEM)
    out = resample.generalize(g, g.cell * 4, method)
    assert out.cell == g.cell * 4 and (out.x0, out.y0) == (g.x0, g.y0)
    assert out.shape == resample.output_shape(g.shape, g.cell, g.cell * 4)
    valid = out.data != out.nodata
    ok = g.data[g.data != g.nodata] if g.nodata is not None else g.data
    assert valid.mean() > 0.9
    assert ok.min() - 1 <= out.data[valid].min() and out.data[valid].max() <= ok.max() + 5   # cubic may overshoot a little


def test_generalize_average_is_block_mean():
    z = np.arange(64, dtype=np.float32).reshape(8, 8)
    g = dio.Grid(z, 1000.0, 2000.0, 2.0, -9999.0, "")
    out = resample.generalize(g, 4.0, "average")
    expect = z.reshape(4, 2, 4, 2).mean(axis=(1, 3))
    assert np.allclose(out.data, expect)
    z2 = z.copy(); z2[0, 0] = -9999.0                                  # NoData is ignored, not averaged
    out2 = resample.generalize(g.like(z2, -9999.0), 4.0, "average")
    assert np.isclose(out2.data[0, 0], np.mean([1, 8, 9]))


def test_generalize_median_and_fractional_ratio():
    z = np.arange(64, dtype=np.float32).reshape(8, 8)
    g = dio.Grid(z, 1000.0, 2000.0, 2.0, -9999.0, "")
    med = resample.generalize(g, 4.0, "median")
    assert np.allclose(med.data, np.median(z.reshape(4, 2, 4, 2), axis=(1, 3)))
    z2 = z.copy(); z2[0, 1] = 1e6                                      # a spike: the median ignores it, the mean does not
    med2 = resample.generalize(g.like(z2, -9999.0), 4.0, "median")
    avg2 = resample.generalize(g.like(z2, -9999.0), 4.0, "average")
    assert med2.data[0, 0] < 20 and avg2.data[0, 0] > 1e5
    fr = resample.generalize(g, 3.0, "average")                       # ratio 1.5: area-weighted mean
    assert fr.shape == (5, 5)
    w = np.array([1.0, 0.5])                                         # first output cell: rows/cols 0 (full) and 1 (half)
    expect = (np.outer(w, w) * z[:2, :2]).sum() / np.outer(w, w).sum()
    assert np.isclose(fr.data[0, 0], expect)
    const = resample.generalize(g.like(np.full((8, 8), 7.0, np.float32), -9999.0), 2.7, "average")
    assert np.allclose(const.data, 7.0)


def test_generalize_refuses_finer_cell_and_unknown_method():
    g = dio.read_raster(DEM)
    with pytest.raises(ValueError):
        resample.generalize(g, g.cell, "average")
    with pytest.raises(ValueError):
        resample.generalize(g, g.cell * 2, "nearest-ish")


def test_pipeline_generalization_and_threshold_rescaling(tmp_path):
    g = dio.read_raster(DEM)
    lines = []
    res = pipeline.run(pipeline.Params(str(DEM), str(tmp_path / "g"), threshold=50, generalize_cell=g.cell * 2,
                                       write_network=False, write_high_density=False), log=lines.append)
    assert res.grid.cell == g.cell * 2
    assert (tmp_path / "g" / "DTM_generalized.tif").exists()
    assert any("rescaled 50 -> 25" in s for s in lines)
    keep = pipeline.run(pipeline.Params(str(DEM), str(tmp_path / "k"), threshold=50, generalize_cell=g.cell * 2,
                                        generalize_rescale_threshold=False, write_network=False, write_high_density=False), **QUIET)
    assert (keep.src == 1).sum() < (res.src == 1).sum()               # unscaled threshold -> sparser network


def test_fine_dtm_warning(tmp_path):
    lines = []
    pipeline.run(pipeline.Params(str(DEM), str(tmp_path / "w"), threshold=50, resolution=2.0,
                                 write_network=False, write_high_density=False), log=lines.append)
    assert any(s.startswith("WARNING: cell size 2 m") for s in lines)


def test_config_roundtrip_and_old_configs(tmp_path):
    par = pipeline.Params("a.tif", "out", s_stop=0.07, wb_exp=-0.25, generalize_cell=10.0, generalize_method="median",
                          generalize_rescale_threshold=False)
    config.save(tmp_path / "c.json", par, part2.RunoutParams(), True)
    p2, _, _ = config.load(tmp_path / "c.json")
    assert (p2.s_stop, p2.wb_exp, p2.generalize_cell, p2.generalize_method, p2.generalize_rescale_threshold) == \
        (0.07, -0.25, 10.0, "median", False)
    d = json.loads((tmp_path / "c.json").read_text())                 # a 0.3.x configuration has none of the new keys
    for k in ("s_max", "s_dep_max", "s_stop", "wb_k", "wb_exp", "area_max_km2", "generalize_cell", "generalize_method",
              "generalize_rescale_threshold"):
        d["procedure"].pop(k)
    (tmp_path / "old.json").write_text(json.dumps(d))
    p3, _, _ = config.load(tmp_path / "old.json")
    assert (p3.s_stop, p3.wb_k, p3.generalize_cell) == (classify.S_STOP, classify.WB_K, None)


def test_cli_advanced_options_and_config_precedence(tmp_path):
    cfg = tmp_path / "cfg.json"
    assert cli.main(["run", str(DEM), "-o", str(tmp_path / "o1"), "--s-stop", "0.07", "--generalize", "10",
                     "--generalize-method", "median", "--no-network", "--quiet", "--save-config", str(cfg)]) == 0
    pr = json.loads(cfg.read_text())["procedure"]
    assert (pr["s_stop"], pr["generalize_cell"], pr["generalize_method"]) == (0.07, 10.0, "median")
    assert (tmp_path / "o1" / "DTM_generalized.tif").exists()
    cfg2 = tmp_path / "cfg2.json"                                     # explicit option overrides the JSON, the rest is kept
    assert cli.main(["run", "--config", str(cfg), "-o", str(tmp_path / "o2"), "--s-stop", "0.06", "--quiet",
                     "--save-config", str(cfg2)]) == 0
    pr2 = json.loads(cfg2.read_text())["procedure"]
    assert (pr2["s_stop"], pr2["generalize_cell"], pr2["generalize_method"]) == (0.06, 10.0, "median")
    with pytest.raises(SystemExit):
        cli.main(["run", str(DEM), "-o", str(tmp_path / "o3"), "--generalize-method", "nearest"])


def test_gui_advanced_tab(tmp_path):
    pytest.importorskip("PySide6")
    pytest.importorskip("matplotlib")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from dfcc.gui import app as A
    qa = QApplication.instance() or QApplication([])
    w = A.MainWindow()
    assert w.side_tabs.tabText(1) == "Advanced"
    par = pipeline.Params("x.tif", "o", s_dep_max=0.2, s_stop=0.08, area_exp=0.4, generalize_cell=7.5, generalize_method="cubic",
                          generalize_rescale_threshold=False)
    w.set_params(par, part2.RunoutParams(), True)
    p2, _, _ = w.params()
    assert (p2.s_dep_max, p2.s_stop, p2.area_exp, p2.generalize_cell, p2.generalize_method, p2.generalize_rescale_threshold) == \
        (0.2, 0.08, 0.4, 7.5, "cubic", False)
    assert "●" in w.side_tabs.tabText(1) and "NOT the standard" in w.adv_state.text()
    w.adv["s_stop"].setValue(0.5)
    with pytest.raises(ValueError):
        w.params()
    w._adv_reset()
    p3, _, _ = w.params()
    assert (p3.s_stop, p3.s_dep_max, p3.area_exp, p3.generalize_cell) == (classify.S_STOP, classify.S_DEP_MAX, 0.5, None)
    assert w.side_tabs.tabText(1) == "Advanced"
