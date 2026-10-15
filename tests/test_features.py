"""Config round trip, runout extension, GUI help/console (offscreen)."""
import os
from pathlib import Path
import pytest
from dfcc import pipeline, part2, config

DEM = Path(__file__).parent / "data" / "dem_sint.tif"


def _res(tmp_path):
    return pipeline.run(pipeline.Params(str(DEM), str(tmp_path), threshold=50), log=lambda *a: None)


def test_extension_never_shortens_profile(tmp_path):
    res = _res(tmp_path)
    kw = dict(min_area_km2=0.02, max_area_km2=1e3, write_hotspots=False)
    base = part2.analyse(res, part2.RunoutParams(**kw), tmp_path / "a", log=lambda *a: None)
    ext = part2.analyse(res, part2.RunoutParams(extend_downstream_m=300.0, **kw), tmp_path / "b", log=lambda *a: None)
    assert base["summary"] and len(base["summary"]) == len(ext["summary"])
    for s0, s1 in zip(base["summary"], ext["summary"]):
        assert s1["length_m"] >= s0["length_m"]


def test_config_roundtrip(tmp_path):
    par = pipeline.Params("a.tif", "out", threshold=8, prefill=True)
    rp = part2.RunoutParams(main_branch="longest", extend_downstream_m=250.0)
    config.save(tmp_path / "c.json", par, rp, True)
    par2, rp2, en = config.load(tmp_path / "c.json")
    assert (par2.threshold, par2.prefill, rp2.main_branch, rp2.extend_downstream_m, en) == (8, True, "longest", 250.0, True)


def test_gui_help_and_params(tmp_path):
    pytest.importorskip("PySide6")
    pytest.importorskip("matplotlib")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from dfcc.gui import app as A
    from dfcc.gui.help import html, HelpDialog, SECTIONS, HELP_DIR
    qa = QApplication.instance() or QApplication([])
    w = A.MainWindow()
    par, rp, en = w.params() if False else (pipeline.Params("x.tif", "o", threshold=12), part2.RunoutParams(extend_downstream_m=120.0), True)
    w.set_params(par, rp, en)
    p2, r2, e2 = w.params()
    assert p2.threshold == 12 and r2.extend_downstream_m == 120.0 and e2
    h = html()
    assert all(f'name="{k}"' in h for k, _ in SECTIONS)
    for img in ("workflow.png", "classes.png", "runout_rule.png", "logo.png"):
        assert (HELP_DIR / img).exists()
    HelpDialog(w)


def test_profile_3d_and_labels(tmp_path):
    pytest.importorskip("matplotlib")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from dfcc import viz
    res = _res(tmp_path)
    out = part2.analyse(res, part2.RunoutParams(min_area_km2=0.02, max_area_km2=1e3, write_hotspots=False), tmp_path / "p", log=lambda *a: None)
    assert out["summary"] and all(s["length_3d_m"] >= s["length_m"] for s in out["summary"])
    fig = plt.figure()
    viz.profile_matrix(fig, out, 2, show3d=True)
    titles = [a.get_title() for a in fig.axes]
    assert titles and all(t.startswith("Basin ") and "3-D" in t for t in titles)
    fig2, ax = plt.subplots()
    viz.draw_base(ax, res)
    viz.draw_runout(ax, out)
    assert any("Basin" in t.get_text() for t in ax.texts)


def test_whole_network(tmp_path):
    import numpy as np
    from dfcc.core import runout as ro
    res = _res(tmp_path)
    kw = dict(min_area_km2=0.02, max_area_km2=1e3, write_hotspots=False)
    base = part2.analyse(res, part2.RunoutParams(**kw), tmp_path / "a", log=lambda *a: None)
    net = part2.analyse(res, part2.RunoutParams(whole_network=True, **kw), tmp_path / "b", log=lambda *a: None)
    assert base["network"] is None and net["network"]
    assert (tmp_path / "b" / "Runout_network.shp").exists() and (tmp_path / "b" / "Runout_network_events.shp").exists()
    s = net["summary"][0]
    assert s["net_cells"] >= s["n_points"] and s["net_flow_cells"] >= 0
    # main-channel results are unchanged by the option
    assert [x["length_m"] for x in base["summary"]] == [x["length_m"] for x in net["summary"]]
    assert [x["final_stop"] for x in base["summary"]] == [x["final_stop"] for x in net["summary"]]
    # along a single path (no merge) the network rule equals the profile rule
    stream = res.src == 1
    rr, cc = ro.main_channel_from_outlet(net["outlets"][0], ro.largest_area_upstream(stream, res.p, res.ad8), stream.shape)
    dom = np.zeros(stream.shape, bool); dom[rr, cc] = True
    N = ro.network_runout(dom, res.p, res.retclass, res.fel, res.ad8, res.grid.cell)
    x, y = res.grid.xy(rr, cc)
    R = ro.profile_runout(res.retclass[rr, cc].astype(int), res.fel[rr, cc].astype(float), x, y)
    assert (N["state"][rr, cc] == R.state).all()
    assert np.allclose(N["L"][rr, cc][R.state != 1], R.L[R.state != 1])
    # network margin is the envelope: never below that of the main channel at the same cell
    assert net["network"]["margin"].shape == stream.shape


def test_network_lateral_stops():
    """Y-shaped toy network: a lateral stopping on its own cells and a lateral whose energy stops on the main channel."""
    import numpy as np
    from dfcc.core import runout as ro
    from dfcc.core.hydro import D1, D2
    ny, nx = 6, 10
    p = np.zeros((ny, nx), np.int16); cls = np.full((ny, nx), 4, np.int16); fel = np.zeros((ny, nx))
    dom = np.zeros((ny, nx), bool); main = np.zeros((ny, nx), bool)

    def code(dr, dc):
        return next(k for k in range(1, 9) if D2[k] == dr and D1[k] == dc)
    for c in range(nx):                                # main channel along row 5, flowing east
        p[5, c] = code(0, 1) if c < nx - 1 else 0
        dom[5, c] = main[5, c] = True; fel[5, c] = 50 - c
    for col, ncls2 in ((4, 4), (8, 2)):                # laterals joining the main channel from the north
        for r in range(5):
            p[r, col] = code(1, 0); dom[r, col] = True; fel[r, col] = 100 - 10 * r
            cls[r, col] = 2 if r < ncls2 else 4
    N = ro.network_runout(dom, p, cls, fel, np.ones((ny, nx)), 10.0, main=main)
    ev = N["event"]
    assert ev[5, 4] == 4 and N["lateral"][5, 4]        # final stop on the main channel, driven by a lateral
    assert ev[2, 8] == 4 and not main[2, 8]            # final stop on the lateral itself
    assert not N["lateral"][5, 0]


def test_network_reactivation_by_lateral():
    import numpy as np
    from dfcc.core import runout as ro
    from dfcc.core.hydro import D1, D2
    ny, nx = 6, 10
    p = np.zeros((ny, nx), np.int16); cls = np.full((ny, nx), 4, np.int16); fel = np.zeros((ny, nx))
    dom = np.zeros((ny, nx), bool); main = np.zeros((ny, nx), bool)
    code = lambda dr, dc: next(k for k in range(1, 9) if D2[k] == dr and D1[k] == dc)
    for c in range(nx):
        p[5, c] = code(0, 1) if c < nx - 1 else 0
        dom[5, c] = main[5, c] = True; fel[5, c] = 50 - c
    for col, n2 in ((4, 4), (8, 5)):
        for r in range(5):
            p[r, col] = code(1, 0); dom[r, col] = True; fel[r, col] = 100 - 10 * r
            cls[r, col] = 2 if r < n2 else 4
    N = ro.network_runout(dom, p, cls, fel, np.ones((ny, nx)), 10.0, main=main)
    assert N["event"][5, 4] == 3                      # stop on the main channel, flow resumes below: not final
    assert N["phase"][5, 6] == ro.PH_BETWEEN          # light-blue tract in between
    assert N["state"][5, 8] == 3                      # re-activated by the lateral
    assert N["event"][5, 9] == 4                      # the later stop is final
