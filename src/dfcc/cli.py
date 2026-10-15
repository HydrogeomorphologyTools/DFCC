"""Command line interface:  dfcc run | fill | gui"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from . import __version__


def _add_run(sp):
    p = sp.add_parser("run", help="run the DFCC procedure on a DTM",
                      description="DFCC: classified channel network, initiation density, 3-D network, optional runout.")
    p.add_argument("dtm", nargs="?", help="input DTM (GeoTIFF, projected CRS, square cells)")
    p.add_argument("-o", "--outdir", help="output folder")
    p.add_argument("--config", help="load all parameters from a JSON file (command-line options override)")
    p.add_argument("--save-config", help="write the effective parameters to a JSON file")
    p.add_argument("-t", "--threshold", type=float, default=50.0, help="slope-area threshold for channel extraction (default 50)")
    p.add_argument("-r", "--resolution", type=float, default=None, help="cell size (default: read from the DTM)")
    p.add_argument("--prefill", action="store_true", help="fill depressions before the procedure (optional pre-processing)")
    p.add_argument("--kd-radius", type=float, default=50.0, help="kernel-density search radius in map units (default 50)")
    p.add_argument("--keep-intermediate", action="store_true", help="also write fel, p, slp, sd8, ad8, sa, ssa, src, inDF")
    p.add_argument("--no-network", action="store_true", help="skip the vector network (Network3D)")
    p.add_argument("--prefix", default="", help="output file prefix")
    g = p.add_argument_group("part 2: main channel, runout and hot-spot points")
    g.add_argument("--runout", action="store_true", help="compute main channel + runout per basin and initiation hot-spot points")
    g.add_argument("--min-area", type=float, default=1.0, help="min basin area km2 (default 1)")
    g.add_argument("--max-area", type=float, default=20.0, help="max basin area km2 (default 20)")
    g.add_argument("--split-area", type=float, default=2.0, help="split at confluences whose branches both exceed this area km2 (default 2)")
    g.add_argument("--pour-points", help="shapefile of basin pour points (overrides automatic selection)")
    g.add_argument("--energy-factor", type=float, default=0.4, help="stop when K > factor*L (default 0.4)")
    g.add_argument("--min-restart-len", type=float, default=30.0, help="restarts dying within this length (m) are spurious (default 30)")
    g.add_argument("--main-branch", choices=["area", "longest", "highest"], default="area")
    g.add_argument("--start-at-head", action="store_true")
    g.add_argument("--extend-downstream", type=float, default=0.0, help="continue the profile this many metres past the basin outlet (e.g. over a fan)")
    g.add_argument("--extend-polygon", help="polygon shapefile (catchment + fan): the extension stops at its border")
    g.add_argument("--whole-network", action="store_true", help="also run the energy rule on every channel of the selected basins (worst-case merge at confluences)")
    g.add_argument("--no-hotspots", action="store_true")
    g.add_argument("--hotspot-snap", type=float, default=50.0)
    g.add_argument("--no-prune", action="store_true", help="keep all hot-spot points (no alignment pruning)")
    p.add_argument("--quiet", action="store_true")
    return p


def ap_defaults(parser):
    m = {"threshold": "threshold", "resolution": "resolution", "prefill": "prefill", "kd_radius": "kd_radius",
         "keep_intermediate": "keep_intermediate", "prefix": "prefix"}
    return {v: parser.get_default(k) for k, v in m.items()}


def _pour_points(path):
    import shapefile
    r = shapefile.Reader(path)
    return [tuple(s.points[0]) for s in r.shapes()]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dfcc", description="DFCC - Debris-Flow Channel Classification")
    ap.add_argument("--version", action="version", version=f"dfcc {__version__}")
    sp = ap.add_subparsers(dest="cmd")
    sp_run = _add_run(sp)
    f = sp.add_parser("fill", help="fill DTM depressions and write the filled DTM")
    f.add_argument("dtm")
    f.add_argument("output")
    sp.add_parser("gui", help="launch the graphical interface")
    a = ap.parse_args(argv)
    if a.cmd is None or a.cmd == "gui":
        from .gui.app import main as gui_main
        return gui_main()
    if a.cmd == "fill":
        import numpy as np
        from . import io as dio
        from .core import hydro
        g = dio.read_raster(a.dtm)
        nd = g.nodata if g.nodata is not None else -9999.0
        out = hydro.fill_depressions(g.data, nd)
        out[~hydro.valid_mask(g.data, g.nodata)] = nd
        dio.write_raster(a.output, g, out, nd, "float32")
        print("written", a.output)
        return 0
    from . import pipeline, part2, config
    log = (lambda *x: None) if a.quiet else print
    par = pipeline.Params(a.dtm or "", a.outdir or "", a.threshold, a.resolution, a.prefill, a.kd_radius,
                          keep_intermediate=a.keep_intermediate, write_network=not a.no_network or a.runout,
                          prefix=a.prefix)
    rp = part2.RunoutParams(a.min_area, a.max_area, a.split_area, a.energy_factor, a.min_restart_len,
                            a.main_branch, a.start_at_head, _pour_points(a.pour_points) if a.pour_points else None,
                            hotspot_snap_m=a.hotspot_snap, hotspot_prune=not a.no_prune,
                            extend_downstream_m=a.extend_downstream, extend_polygon=a.extend_polygon, whole_network=a.whole_network,
                            write_hotspots=not a.no_hotspots)
    do_runout = a.runout
    if a.config:                                   # JSON first, explicit CLI options win
        par0, rp0, en0 = config.load(a.config)
        defaults = ap_defaults(sp_run)
        for k, v in vars(par0).items():
            if getattr(par, k) == defaults.get(k, getattr(par, k)) or k in ("dtm", "outdir"):
                if k in ("dtm", "outdir") and getattr(par, k):
                    continue
                setattr(par, k, v)
        rp = rp0
        do_runout = do_runout or en0
        par.write_network = par.write_network or do_runout
    if not par.dtm or not par.outdir:
        sp_run.error("dtm and --outdir are required (directly or through --config)")
    if a.save_config:
        config.save(a.save_config, par, rp, do_runout)
        log(f"Configuration saved to {a.save_config}")
    res = pipeline.run(par, log=log)
    if do_runout:
        out = part2.analyse(res, rp, par.outdir, par.prefix, log=log)
        for s in out["summary"]:
            log(f"Basin {s['basin']}: {s['area_km2']} km2, L={s['length_m']} m, final stop: {s['final_stop']}"
                + (f" at {s['final_stop_dist_from_head_m']} m from head" if s["final_stop"] == "yes" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
