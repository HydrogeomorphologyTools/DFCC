"""DFCC main workflow: channel-network characterisation by debris-flow propensity."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import time
import numpy as np

from . import io as dio
from .core import hydro, classify, density, network
from .core.classify import CLASS_NAMES


@dataclass
class Params:
    dtm: str
    outdir: str
    threshold: float = 50.0            # slope-area threshold for channel extraction
    resolution: float | None = None    # cell size (auto from DTM when None)
    prefill: bool = False              # optional ArcGIS-like Fill pre-processing
    kd_radius: float = 50.0            # kernel density search radius (m)
    slope_exp: float = 1.0             # m in S^m A^n
    area_exp: float = 0.5              # n
    keep_intermediate: bool = False
    write_network: bool = True
    write_high_density: bool = True
    prefix: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Result:
    grid: dio.Grid
    fel: np.ndarray
    p: np.ndarray
    slp: np.ndarray
    ad8: np.ndarray
    src: np.ndarray
    retclass: np.ndarray
    indf: np.ndarray
    density: np.ndarray
    high: np.ndarray
    high_break: float
    arcs: list = field(default_factory=list)
    arcs_obj: object = None
    files: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)


def _noop(*a, **k):
    pass


def run(par: Params, log=print, progress=_noop) -> Result:
    out = Path(par.outdir)
    out.mkdir(parents=True, exist_ok=True)
    T = {}
    files = {}

    def tick(name, t0):
        T[name] = time.perf_counter() - t0

    def f(name):
        return str(out / (par.prefix + name))

    t = time.perf_counter()
    g = dio.read_raster(par.dtm)
    cell = float(par.resolution or g.cell)
    nd = g.nodata
    dem = np.ascontiguousarray(g.data, dtype=np.float32)
    valid = hydro.valid_mask(dem, nd)
    ndv = np.float32(nd) if nd is not None else np.float32(-9999.0)
    dem[~valid] = ndv
    tick("read", t)
    log(f"DTM {dem.shape[1]}x{dem.shape[0]}, cell {cell} m, {int(valid.sum())} valid cells")
    log(f"  file: {par.dtm}")
    log(f"  extent: {g.x0:.1f},{g.y0 - dem.shape[0] * cell:.1f} -> {g.x0 + dem.shape[1] * cell:.1f},{g.y0:.1f} | NoData={nd} | CRS {'defined' if g.wkt else 'MISSING'}")
    log(f"  elevation range: {float(dem[valid].min()):.2f} .. {float(dem[valid].max()):.2f} m  ({100.0 * valid.mean():.1f}% valid cells)")
    progress(0.05, "DTM read")

    t = time.perf_counter()
    if par.prefill:
        log("Pre-processing: depression filling")
        dem = hydro.fill_depressions(dem, ndv)
        dem[~valid] = ndv
        if par.keep_intermediate:
            dio.write_raster(f("DTM_prefill.tif"), g, dem, ndv, "float32")
    fel = hydro.fill_depressions(dem, ndv)                      # TauDEM PitRemove
    fel[~valid] = ndv
    tick("fill", t)
    raised = (fel > dem) & valid
    log(f"PitRemove done in {T['fill']:.2f} s: {int(raised.sum())} cells raised (max +{float(np.max(fel[valid] - dem[valid])):.2f} m)")
    progress(0.15, "Pit remove")

    t = time.perf_counter()
    p, sd8 = hydro.d8_flowdir(fel, ndv, cell)
    ang, slp = hydro.dinf_slope(fel, ndv, cell)
    tick("flowdir", t)
    nofl = int((((p < 1) | (p > 8)) & valid).sum())
    log(f"D8 / D-infinity flow directions done in {T['flowdir']:.2f} s ({nofl} outlet/edge cells without a downslope neighbour; max D8 slope {float(sd8[valid].max()):.3f})")
    progress(0.35, "Flow directions")

    t = time.perf_counter()
    ad8 = hydro.area_d8(p)
    sa = hydro.slope_area(sd8, ad8, par.slope_exp, par.area_exp)
    ssa = hydro.max_upslope(p, sa)
    src = hydro.threshold_stream(ssa, par.threshold)
    tick("stream", t)
    log(f"Contributing area D8 / slope-area / upslope maximum done; largest drainage area {float(ad8.max()) * cell * cell / 1e6:.3f} km2")
    log(f"Channel network: {int((src == 1).sum())} cells (threshold {par.threshold}, exponents m={par.slope_exp}, n={par.area_exp})")
    progress(0.5, "Channel network")

    t = time.perf_counter()
    cls, indf = classify.classify_network(src, slp, ad8, cell)
    tick("classify", t)
    counts = {CLASS_NAMES[k]: int((cls == k).sum()) for k in CLASS_NAMES}
    ncl = max(1, int((cls > 0).sum()))
    log(f"Classification ({T['classify']:.2f} s): " + ", ".join(f"{k} {v} ({100.0 * v / ncl:.1f}%)" for k, v in counts.items()))
    progress(0.6, "Classification")

    t = time.perf_counter()
    dens = density.kernel_density(indf, cell, par.kd_radius, 10000.0, valid)
    high, brk = density.high_density_mask(dens, valid)
    tick("density", t)
    log(f"Initiation points: {int(indf.sum())} | max density {float(dens[valid].max()):.2f} points/ha | non-zero cells {int((dens[valid] > 0).sum())}")
    log(f"Kernel density done; natural break = {brk:.4f}, high-density cells = {int(high.sum())}")
    progress(0.7, "Density")

    nodata_f = -3.4028234663852886e+38
    dio.write_raster(f("ClassifiedNetwork.tif"), g, cls, 0, "uint8")
    files["ClassifiedNetwork"] = f("ClassifiedNetwork.tif")
    dio.write_raster(f("InitiationDensity.tif"), g, dens, nodata_f, "float32")
    files["InitiationDensity"] = f("InitiationDensity.tif")
    if par.keep_intermediate:
        for nm, arr, ndv_, dt in (("DTM_fel", fel, ndv, "float32"), ("p", p, -32768, "int16"),
                                  ("slp", slp, -1.0, "float32"), ("sd8", sd8, -1.0, "float32"),
                                  ("ad8", ad8, -1.0, "float32"), ("sa", sa, -1.0, "float32"),
                                  ("ssa", ssa, nodata_f, "float32"), ("src", src, -32768, "int16"),
                                  ("inDF", indf, 0, "uint8")):
            dio.write_raster(f(nm + ".tif"), g, arr, ndv_, dt)
            files[nm] = f(nm + ".tif")

    arcs, arcs_obj = [], None
    if par.write_network:
        t = time.perf_counter()
        arcs, arcs_obj = network.build_network(src, p, fel, float(ndv), (g.x0, g.y0), cell)
        tick("network", t)
        write_network(arcs, arcs_obj, cls, fel, g, f("Network3D.shp"), f("Network_classes.shp"), valid)
        files["Network3D"] = f("Network3D.shp")
        files["Network_classes"] = f("Network_classes.shp")
        log(f"Network vectorised: {len(arcs)} arcs, {sum(float(np.sum(np.hypot(*np.diff(a['xyz'][:, :2], axis=0).T))) for a in arcs) / 1000:.2f} km")
    progress(0.85, "Vector network")

    if par.write_high_density:
        t = time.perf_counter()
        dio.write_raster(f("HighDensity.tif"), g, high.astype(np.uint8), 0, "uint8")
        files["HighDensity_raster"] = f("HighDensity.tif")
        geoms = dio.polygonize_mask(high, g, connectivity=8)
        dio.write_polygons(f("HighDensity.shp"), geoms, [("id", "N", 10, 0), ("area_ha", "F", 14, 4)],
                           [(i + 1, _poly_area(gm) / 1e4) for i, gm in enumerate(geoms)], g.wkt)
        files["HighDensity"] = f("HighDensity.shp")
        tick("polygons", t)
        log(f"High-density areas: {len(geoms)} polygons")
    progress(1.0, "Done")
    for k, v in files.items():
        try:
            log(f"  wrote {Path(v).name} ({Path(v).stat().st_size / 1024:.0f} kB)")
        except OSError:
            pass
    log("Timings (s): " + ", ".join(f"{k}={v:.2f}" for k, v in T.items()))
    return Result(g, fel, p, slp, ad8, src, cls, indf, dens, high, brk, arcs, arcs_obj, files, T)


def _poly_area(geom):
    def ring_area(r):
        r = np.asarray(r)
        return 0.5 * float(np.sum(r[:-1, 0] * r[1:, 1] - r[1:, 0] * r[:-1, 1]))
    rings = geom["coordinates"]
    return abs(ring_area(rings[0])) - sum(abs(ring_area(h)) for h in rings[1:])


def write_network(arcs, arcs_obj, cls, fel, g, path3d, path_cls, valid):
    """Network3D (ESRI-equivalent arcs) and Network_classes (arcs split by DF class)."""
    ny, nx = cls.shape
    dio.write_polylines(path3d, [a["xyz"] for a in arcs],
                        [("arcid", "N", 10, 0), ("grid_code", "N", 10, 0), ("from_node", "N", 10, 0), ("to_node", "N", 10, 0)],
                        [(a["arcid"], 1, a["from_node"], a["to_node"]) for a in arcs], g.wkt)
    lines, recs = [], []
    k = 0
    for a in arcs:
        cells = a["cells"]
        rr, cc = cells // nx, cells % nx
        cl = cls[rr, cc]
        x, y = g.xy(rr, cc)
        z = fel[rr, cc].astype(float)
        pts = np.column_stack([x, y, z])
        start = 0
        for i in range(1, len(cells) + 1):
            if i == len(cells) or cl[i] != cl[start]:
                end = min(i, len(cells) - 1)       # share the boundary cell with the next run
                seg = pts[start:end + 1] if end > start else pts[start:start + 1]
                if len(seg) >= 2:
                    k += 1
                    lines.append(seg)
                    recs.append((k, a["arcid"], int(cl[start]), CLASS_NAMES.get(int(cl[start]), ""), float(np.sum(np.hypot(*np.diff(seg[:, :2], axis=0).T)))))
                start = i
    dio.write_polylines(path_cls, lines,
                        [("id", "N", 10, 0), ("arcid", "N", 10, 0), ("class", "N", 4, 0), ("name", "C", 16), ("length_m", "F", 14, 2)],
                        recs, g.wkt)
