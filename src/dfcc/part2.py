"""Part 2 of DFCC: per-basin main channel, classified profile and morphometric runout."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import numpy as np

from . import io as dio
from .core import runout as ro, hotspots as hs
from .core.classify import CLASS_NAMES
from .core.hydro import D1, D2

def ro_cum3d(x, y, z):
    return np.r_[0.0, np.cumsum(np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2 + np.diff(z) ** 2))]


EVENT_NAMES = {"final_stop_lateral": "Final stop (lateral)", "final_stop_lat_on_main": "Final stop on main channel, lateral-driven",
               "initiation": "Initiation", "restart": "Restart", "spurious_restart": "Spurious restart",
               "stop": "Intermediate stop", "final_stop": "Final stop"}


@dataclass
class RunoutParams:
    min_area_km2: float = 1.0          # smallest basin considered
    max_area_km2: float = 20.0         # procedure validity limit
    split_area_km2: float = 2.0        # confluences where both branches exceed this split the basin
    energy_factor: float = 0.4         # stop when K > factor * L
    min_restart_len_m: float = 30.0    # restarts dying within this length (m) are 'spurious'
    main_branch: str = "area"          # 'area' (largest contributing area at each confluence) | 'longest' | 'highest'
    start_at_head: bool = False        # start energy balance at the headwater even without class-2 cell
    pour_points: list | None = None    # optional [(x, y), ...] overriding automatic basin selection
    snap_m: float = 50.0
    hotspot_snap_m: float = 50.0
    hotspot_prune: bool = True
    write_hotspots: bool = True
    extend_downstream_m: float = 0.0   # continue the profile past the outlet along the network (e.g. over a fan), metres
    extend_polygon: str | None = None  # optional polygon shapefile (catchment + fan): the extension stops at its border
    whole_network: bool = False        # also run the energy rule on every channel of the selected basins (worst-case merge)


def select_basin_outlets(res, rp: RunoutParams):
    """Automatic basin selection: network outlets, split at significant confluences."""
    g = res.grid
    cell = g.cell
    ny, nx = res.src.shape
    stream = res.src == 1
    a_km2 = res.ad8 * np.float32(cell * cell / 1e6)
    cands = {}
    if rp.pour_points:
        rad = int(np.ceil(rp.snap_m / cell))
        for (x, y) in rp.pour_points:
            r, c = g.rowcol(x, y)
            r0, r1, c0, c1 = max(r - rad, 0), min(r + rad + 1, ny), max(c - rad, 0), min(c + rad + 1, nx)
            sub = np.where(stream[r0:r1, c0:c1], res.ad8[r0:r1, c0:c1], -1)
            if sub.max() < 0:
                continue
            i, j = np.unravel_index(int(np.argmax(sub)), sub.shape)
            cands[(r0 + i, c0 + j)] = "pour_point"
        return cands
    for a in res.arcs:
        if a["end_outlet"]:
            c = int(a["cells"][-1])
            cands[(c // nx, c % nx)] = "outlet"
    # significant confluences
    sig_down = set()
    for (rr, cc) in zip(*np.nonzero(stream)):
        ins = hs._inflow_neighbours(int(rr), int(cc), res.p, (ny, nx))
        ins = [i for i in ins if stream[i]]
        big = [i for i in ins if a_km2[i] >= rp.split_area_km2]
        if len(big) >= 2:
            for i in big:
                cands[i] = "confluence"
            r, c = int(rr), int(cc)                      # everything downstream of the confluence is superseded
            while True:
                sig_down.add((r, c))
                k = res.p[r, c]
                if not (1 <= k <= 8):
                    break
                r, c = r + D2[k], c + D1[k]
                if r < 0 or c < 0 or r >= ny or c >= nx or not stream[r, c]:
                    break
    out = {k: v for k, v in cands.items() if k not in sig_down and rp.min_area_km2 <= a_km2[k] <= rp.max_area_km2 * 1.0001}
    return out


def _polygon_mask(path, g, shape):
    import shapefile
    from rasterio import features
    from rasterio.transform import Affine
    geoms = [s.__geo_interface__ for s in shapefile.Reader(path).shapes()]
    return features.rasterize([(gm, 1) for gm in geoms], out_shape=shape,
                              transform=Affine(g.cell, 0, g.x0, 0, -g.cell, g.y0), fill=0, dtype="uint8").astype(bool)


def analyse(res, rp: RunoutParams, outdir, prefix="", log=print):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    g = res.grid
    cell = g.cell
    ny, nx = res.src.shape
    stream = np.ascontiguousarray(res.src == 1)
    outlets = select_basin_outlets(res, rp)
    log(f"Basins selected: {len(outlets)} ({'user pour points' if rp.pour_points else 'automatic: outlets %.1f-%.1f km2, split at confluences >= %.1f km2' % (rp.min_area_km2, rp.max_area_km2, rp.split_area_km2)})")
    order_o = sorted(outlets, key=lambda t: -res.ad8[t])
    labels = ro.basin_labels(res.p, order_o) if order_o else None
    _, up_len, best_up = ro.longest_paths(stream, res.p, cell)
    best_area = ro.largest_area_upstream(stream, res.p, res.ad8)

    ext_mask = _polygon_mask(rp.extend_polygon, g, (ny, nx)) if rp.extend_polygon else None
    def _extension(r0, c0):
        """Cells below the outlet followed along the D8 path (distance / polygon limited)."""
        add_r, add_c = [], []
        if rp.extend_downstream_m > 0 or ext_mask is not None:
            er, ec = ro.downstream_path((int(r0), int(c0)), res.p, stream, (ny, nx))
            dist = 0.0
            for k in range(1, len(er)):
                dist += cell * (1.41421356 if (er[k] != er[k - 1] and ec[k] != ec[k - 1]) else 1.0)
                if (rp.extend_downstream_m > 0 and dist > rp.extend_downstream_m) or (ext_mask is not None and not ext_mask[er[k], ec[k]]):
                    break
                add_r.append(er[k]); add_c.append(ec[k])
        return np.array(add_r, dtype=np.int64), np.array(add_c, dtype=np.int64)

    main_mask = np.zeros((ny, nx), bool)
    prof_pts, prof_rec = [], []
    seg_lines, seg_rec = [], []
    ev_pts, ev_rec = [], []
    summary = []
    for bi, o in enumerate(order_o, start=1):
        if rp.main_branch == "highest":
            m = stream & (labels == bi)
            zz = np.where(m, res.fel, -np.inf)
            h = np.unravel_index(int(np.argmax(zz)), zz.shape)
            rr, cc = ro.downstream_path(h, res.p, stream, (ny, nx))
            keep = np.arange(len(rr))
            # stop at this basin's outlet
            idx = np.where((rr == o[0]) & (cc == o[1]))[0]
            if idx.size:
                rr, cc = rr[:idx[0] + 1], cc[:idx[0] + 1]
        else:
            rr, cc = ro.main_channel_from_outlet(o, best_area if rp.main_branch == "area" else best_up, (ny, nx))
        add_r, add_c = _extension(rr[-1], cc[-1])
        if len(add_r):
            rr, cc = np.concatenate([rr, add_r]), np.concatenate([cc, add_c])
        main_mask[rr, cc] = True
        x, y = g.xy(rr, cc)
        z = res.fel[rr, cc].astype(float)
        cl = res.retclass[rr, cc].astype(int)
        R = ro.profile_runout(cl, z, x, y, rp.energy_factor, rp.min_restart_len_m, rp.start_at_head)
        area = float(res.ad8[o]) * cell * cell / 1e6
        log(f"Basin {bi}: outlet at ({x[-1]:.1f}, {y[-1]:.1f}), area {area:.3f} km2, main channel '{rp.main_branch}': {len(rr)} cells, head {z[0]:.1f} m -> outlet {z[-1]:.1f} m")
        length = float(R.cum_dist[-1])
        final = R.final_stop
        log(f"  classes on the channel: " + ", ".join(f"{CLASS_NAMES[k]} {int((cl == k).sum())}" for k in (2, 1, 3, 4)) +
            f" | stops {len(R.stops)}, restarts {int(sum(e == 'restart' for e in R.event))}, spurious {int(sum(e == 'spurious_restart' for e in R.event))}")
        log(f"  final stop: " + (f"cell {final} at {float(R.cum_dist[final]):.0f} m from the head (z={float(z[final]):.1f} m)" if final is not None else "none (flow reaches the end of the profile)"))
        summary.append(dict(
            basin=bi, kind=outlets[o], area_km2=round(area, 4), x_outlet=float(x[-1]), y_outlet=float(y[-1]),
            head_elev_m=float(z[0]), outlet_elev_m=float(z[-1]), length_m=round(length, 2), length_3d_m=round(float(ro_cum3d(x, y, z)[-1]), 2),
            n_points=len(rr), n_initiation_cells=int((cl == 2).sum()),
            n_stops=len(R.stops), n_restarts=int(sum(e == "restart" for e in R.event)),
            n_spurious_restarts=int(sum(e == "spurious_restart" for e in R.event)),
            final_stop="yes" if final is not None else "no",
            final_stop_dist_from_head_m=round(float(R.cum_dist[final]), 2) if final is not None else None,
            final_stop_dist_to_outlet_m=round(length - float(R.cum_dist[final]), 2) if final is not None else None,
            final_stop_x=float(x[final]) if final is not None else None,
            final_stop_y=float(y[final]) if final is not None else None,
            final_stop_elev_m=float(z[final]) if final is not None else None,
            flow_reaches_outlet="yes" if (final is None and R.state[-1] == ro.FLOW) else "no"))
        for i in range(len(rr)):
            prof_pts.append((x[i], y[i]))
            prof_rec.append((bi, i + 1, float(x[i]), float(y[i]), float(z[i]), int(cl[i]), int(R.state[i]),
                             R.event[i], float(R.dist[i]), float(R.drop[i]), float(R.L[i]), float(R.K[i]), float(R.cum_dist[i])))
            if R.event[i]:
                ev_pts.append((x[i], y[i]))
                ev_rec.append((bi, R.event[i], EVENT_NAMES[R.event[i]], float(z[i]), float(R.cum_dist[i]), i + 1))
        # coloured, class-split polyline (class along the profile; stopped/ no-flow marked by df_yn)
        s = 0
        for i in range(1, len(rr) + 1):
            if i == len(rr) or cl[i] != cl[s] or R.state[i] != R.state[s] or R.phase[i] != R.phase[s]:
                e = min(i, len(rr) - 1)
                if e > s:
                    seg_lines.append(np.column_stack([x[s:e + 1], y[s:e + 1], z[s:e + 1]]))
                    seg_rec.append((bi, int(cl[s]), CLASS_NAMES.get(int(cl[s]), ""), int(R.state[s]), int(R.phase[s]),
                                    float(R.cum_dist[s]), float(R.cum_dist[e])))
                s = i
    net = None
    if rp.whole_network and order_o:
        net = _whole_network(res, rp, order_o, labels, stream, _extension, summary, log, main_mask)
    log(f"Writing runout shapefiles ({len(seg_lines)} segments, {len(ev_pts)} events, {len(prof_pts)} profile points)")
    wkt = g.wkt
    P = lambda n: str(out / (prefix + n))
    dio.write_polylines(P("Runout_mainchannel.shp"), seg_lines,
                        [("basin", "N", 6, 0), ("class", "N", 3, 0), ("name", "C", 16), ("df_yn", "N", 2, 0), ("phase", "N", 2, 0),
                         ("d_from", "F", 12, 2), ("d_to", "F", 12, 2)], seg_rec, wkt)
    dio.write_points(P("Runout_events.shp"), ev_pts,
                     [("basin", "N", 6, 0), ("event", "C", 20), ("descr", "C", 24), ("elev", "F", 12, 2),
                      ("dist_m", "F", 12, 2), ("idx", "N", 8, 0)], ev_rec, wkt)
    dio.write_points(P("Runout_points.shp"), prof_pts,
                     [("basin", "N", 6, 0), ("idx", "N", 8, 0), ("X", "F", 14, 3), ("Y", "F", 14, 3), ("DTM", "F", 10, 3),
                      ("ClassNet", "N", 3, 0), ("DF_YN", "N", 2, 0), ("event", "C", 20), ("dist", "F", 10, 3),
                      ("delta_h", "F", 10, 3), ("L_drop", "F", 10, 3), ("K_dist", "F", 10, 3), ("cumdist", "F", 12, 2)],
                     prof_rec, wkt)
    import csv
    if summary:
        with open(P("Runout_summary.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(summary[0].keys()), delimiter=";")
            w.writeheader()
            w.writerows(summary)
    if net:
        dio.write_polylines(P("Runout_network.shp"), net["lines"],
                            [("basin", "N", 6, 0), ("class", "N", 3, 0), ("name", "C", 16), ("df_yn", "N", 2, 0), ("phase", "N", 2, 0), ("main", "N", 2, 0),
                             ("L_drop", "F", 10, 2), ("K_dist", "F", 10, 2), ("margin", "F", 10, 2)], net["lrec"], wkt)
        dio.write_points(P("Runout_network_events.shp"), net["ev_pts"],
                         [("basin", "N", 6, 0), ("event", "C", 24), ("descr", "C", 44), ("elev", "F", 12, 2)], net["ev_rec"], wkt)
    files = {"Runout_mainchannel": P("Runout_mainchannel.shp"), "Runout_events": P("Runout_events.shp"),
             "Runout_points": P("Runout_points.shp"), "Runout_summary": P("Runout_summary.csv")}
    if net:
        files["Runout_network"] = P("Runout_network.shp"); files["Runout_network_events"] = P("Runout_network_events.shp")
    hot = []
    if rp.write_hotspots:
        hot = hs.find_hotspots(res.high, res.src, res.p, res.ad8, res.fel, res.density, cell,
                               rp.hotspot_snap_m, rp.hotspot_prune)
        xy = [g.xy(d["row"], d["col"]) for d in hot]
        fields = [("id", "N", 8, 0), ("patch", "N", 8, 0), ("z", "F", 10, 2), ("area_km2", "F", 12, 4),
                  ("dens", "F", 10, 3), ("snapped", "N", 2, 0), ("keep", "N", 2, 0), ("dropped_by", "N", 8, 0)]
        recs = [(d["id"], d["patch"], d["z"], d["area_km2"], d["dens"], int(d["snapped"]), int(d["keep"]), d["dropped_by"]) for d in hot]
        dio.write_points(P("InitiationPoints_candidates.shp"), xy, fields, recs, wkt)
        kept = [i for i, d in enumerate(hot) if d["keep"]]
        dio.write_points(P("InitiationPoints_MSF.shp"), [xy[i] for i in kept], fields, [recs[i] for i in kept], wkt)
        files["InitiationPoints_candidates"] = P("InitiationPoints_candidates.shp")
        files["InitiationPoints_MSF"] = P("InitiationPoints_MSF.shp")
        log(f"Hot-spot points: {len(hot)} candidates, {len(kept)} kept")
    return dict(summary=summary, files=files, hotspots=hot, outlets=order_o,
                profiles=prof_rec, segments=(seg_lines, seg_rec), events=(ev_pts, ev_rec), network=net)


def _whole_network(res, rp, order_o, labels, stream, extension, summary, log, main_mask):
    """Energy rule on every channel cell of the selected basins (+ optional extension below the outlets)."""
    g = res.grid
    cell = g.cell
    ny, nx = stream.shape
    lab = np.where(stream, labels, 0).astype(np.int32)
    for bi, o in enumerate(order_o, start=1):
        ar, ac = extension(o[0], o[1])
        for r, c in zip(ar, ac):
            if lab[r, c] == 0:
                lab[r, c] = bi
    dom = lab > 0
    log(f"Whole-network runout: {int(dom.sum())} channel cells in {len(order_o)} basins")
    N = ro.network_runout(dom, res.p, res.retclass, res.fel, res.ad8, cell, rp.energy_factor, rp.min_restart_len_m, main=main_mask)
    st, ev = N["state"], N["event"]
    ev_key = {1: "initiation", 2: "restart", 3: "stop", 4: "final_stop", 9: "spurious_restart"}
    lines, lrec, ev_pts, ev_rec = [], [], [], []
    rows, cols = np.where(dom)
    for r, c in zip(rows, cols):
        k = res.p[r, c]
        if 1 <= k <= 8:
            rr, cc = r + D2[k], c + D1[k]
            if 0 <= rr < ny and 0 <= cc < nx and dom[rr, cc]:
                x0, y0 = g.xy(r, c); x1, y1 = g.xy(rr, cc)
                lines.append(np.array([[x0, y0, float(res.fel[r, c])], [x1, y1, float(res.fel[rr, cc])]]))
                cl = int(res.retclass[rr, cc])
                lrec.append((int(lab[rr, cc]), cl, CLASS_NAMES.get(cl, ""), int(st[rr, cc]), int(N["phase"][rr, cc]), int(main_mask[r, c] and main_mask[rr, cc]), float(N["L"][rr, cc]), float(N["K"][rr, cc]), float(N["margin"][rr, cc])))
        e = int(ev[r, c])
        if e:
            x0, y0 = g.xy(r, c)
            ev_pts.append((x0, y0))
            k_ = ev_key[e]
            if e == 4 and not main_mask[r, c]:
                k_ = "final_stop_lateral"
            elif e == 4 and N["lateral"][r, c]:
                k_ = "final_stop_lat_on_main"
            ev_rec.append((int(lab[r, c]), k_, EVENT_NAMES[k_], float(res.fel[r, c])))
    for s_ in summary:
        b = s_["basin"]
        m = lab == b
        flow = m & (st == 3)
        o = order_o[b - 1]
        s_["net_cells"] = int(m.sum())
        s_["net_flow_cells"] = int(flow.sum())
        s_["net_flow_length_km"] = round(float(flow.sum()) * cell / 1e3, 3)
        s_["net_initiations"] = int(((ev == 1) & m).sum())
        s_["net_restarts"] = int(((ev == 2) & m).sum())
        s_["net_spurious_restarts"] = int(((ev == 9) & m).sum())
        s_["net_stops"] = int((((ev == 3) | (ev == 4)) & m).sum())
        s_["net_final_stops"] = int(((ev == 4) & m).sum())
        s_["net_final_stops_main"] = int(((ev == 4) & m & main_mask & ~N["lateral"]).sum())
        s_["net_final_stops_lateral"] = int(((ev == 4) & m & ~(main_mask & ~N["lateral"])).sum())
        s_["net_outlet_state"] = {1: "no flow", 2: "stop", 3: "flow"}[int(st[o])]
        s_["net_outlet_margin_m"] = round(float(N["margin"][o]), 2)
        log(f"  Basin {b}: network {s_['net_cells']} cells, flowing {s_['net_flow_cells']}, stops {s_['net_stops']} (final {s_['net_final_stops']}), outlet: {s_['net_outlet_state']}; final stops: main {s_['net_final_stops_main']}, lateral/lateral-driven {s_['net_final_stops_lateral']}")
    return dict(lines=lines, lrec=lrec, ev_pts=ev_pts, ev_rec=ev_rec, state=st, event=ev, labels=lab, margin=N["margin"], phase=N["phase"], grid=g)
