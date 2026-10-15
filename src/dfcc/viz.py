"""Matplotlib helpers shared by the GUI and the report images (alpine palette)."""
from __future__ import annotations
import numpy as np
from matplotlib.colors import ListedColormap, LightSource, BoundaryNorm
from matplotlib.lines import Line2D
from .core.classify import CLASS_COLORS, CLASS_NAMES

PALETTE = dict(bg="#0e1a24", panel="#16293a", ink="#e8f1f7", muted="#8aa4b8", ice="#7fd1f2",
               snow="#f4f9fc", rock="#c9b79c", ember="#f4723c", moss="#3fae5a")
CLASS_CMAP = ListedColormap([CLASS_COLORS[k] for k in (1, 2, 3, 4)])
EVENT_STYLE = {"initiation": ("^", "#e63946", "Initiation"), "stop": ("s", "#f77f00", "Intermediate stop"),
               "restart": ("v", "#ff7b7b", "Restart"), "spurious_restart": ("x", "#888888", "Spurious restart"),
               "final_stop": ("X", "#2a9d3c", "Final stop"),
               "final_stop_lateral": ("D", "#8e44ad", "Final stop (lateral)"),
               "final_stop_lat_on_main": ("P", "#c2185b", "Final stop on main channel, driven by a lateral")}
# tract colours shared by main-channel runout and whole-network runout (same order as core.runout PH_*)
PHASE_COLORS = {1: "#ffd60a", 2: "#1f6feb", 3: "#f77f00", 4: "#6ec6ff", 5: "#2a9d3c"}
PHASE_LABELS = {1: "Not activated (upstream of initiation)", 2: "Runout: flow", 3: "Stop (intermediate or final)",
                4: "Stopped, flow resumes downstream", 5: "After final stop"}


def hillshade(dem, cell, valid=None, az=315, alt=40, vert_exag=1.0):
    d = np.where(valid, dem, np.nan) if valid is not None else dem.astype(float)
    fill = np.nanmin(d) if np.isfinite(d).any() else 0
    ls = LightSource(azdeg=az, altdeg=alt)
    hs = ls.hillshade(np.nan_to_num(d, nan=fill), vert_exag=vert_exag, dx=cell, dy=cell)
    if valid is not None:
        hs = np.where(valid, hs, np.nan)
    return hs


def extent(grid):
    ny, nx = grid.shape
    return (grid.x0, grid.x0 + nx * grid.cell, grid.y0 - ny * grid.cell, grid.y0)


def draw_base(ax, res, window=None):
    g = res.grid
    ny, nx = res.fel.shape
    valid = res.fel > -1e30
    hs = hillshade(res.fel, g.cell, valid)
    ext = extent(g)
    ax.imshow(hs, cmap="gray", extent=ext, vmin=0.1, vmax=1.0, interpolation="bilinear", zorder=0)
    ax.set_facecolor(PALETTE["bg"])
    ax.set_aspect("equal")
    ax.tick_params(colors=PALETTE["muted"], labelsize=7)
    for s in ax.spines.values():
        s.set_color(PALETTE["muted"])
    return ext


def draw_network(ax, res, lw=1.3, alpha=1.0):
    """Classified network drawn as coloured polylines through the cell centres."""
    from matplotlib.collections import LineCollection
    g = res.grid
    ny, nx = res.retclass.shape
    segs, cols = [], []
    for a in res.arcs:
        c = a["cells"]
        if len(c) < 2:
            continue
        rr, cc = c // nx, c % nx
        x, y = g.xy(rr, cc)
        k = res.retclass[rr, cc]
        P = np.column_stack([x, y])
        for i in range(len(c) - 1):
            segs.append(P[i:i + 2])
            cols.append(CLASS_COLORS.get(int(k[i + 1]), "#1f5fbf"))
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=lw, zorder=3, capstyle="round", alpha=alpha))


def draw_density(ax, res, alpha=0.65):
    g = res.grid
    d = np.ma.masked_where((res.density <= 0) | (res.density < -1e30), res.density)
    ax.imshow(d, cmap="YlOrRd", alpha=alpha, extent=extent(g), interpolation="nearest", zorder=2)


def draw_high(ax, res, color="#ff2d55"):
    g = res.grid
    m = np.ma.masked_where(~res.high, res.high.astype(float))
    ax.contour(np.flipud(res.high.astype(float)), levels=[0.5], colors=color, linewidths=0.8,
               extent=extent(g), zorder=4, origin="lower")


def class_legend(ax, loc="lower left"):
    h = [Line2D([0], [0], color=CLASS_COLORS[k], lw=3, label=CLASS_NAMES[k].capitalize()) for k in (2, 1, 3, 4)]
    leg = ax.legend(handles=h, loc=loc, fontsize=7, facecolor=PALETTE["panel"], edgecolor=PALETTE["muted"], labelcolor=PALETTE["ink"])
    ax.add_artist(leg)                # keep it when further legends are added
    return leg


def _phase_lw(ph, lw):
    return lw * 0.6 if ph == 1 else lw


def draw_runout(ax, out, lw=2.6, show_labels=True, underlay=False):
    """Main-channel runout: tracts coloured by phase (yellow = not yet activated, blue = flow, orange = stop,
    light blue = stopped but flow resumes downstream, green = after the final stop) + events.
    Returns the set of event keys drawn."""
    seg_lines, seg_rec = out["segments"]
    for ln, rec in zip(seg_lines, seg_rec):
        ph = rec[4]
        ax.plot(ln[:, 0], ln[:, 1], color=PHASE_COLORS.get(ph, "#ffffff"), lw=_phase_lw(ph, lw), zorder=6,
                solid_capstyle="round")
    if show_labels:
        for b in sorted({r[0] for r in out["profiles"]}):
            rows = [r for r in out["profiles"] if r[0] == b]
            r = rows[len(rows) // 2]
            info = next((q for q in out.get("summary", []) if q.get("basin") == b), None)
            txt = f"Basin {b}" + (f"\n{info['area_km2']:.2f} km²" if info else "")
            ax.annotate(txt, (r[2], r[3]), xytext=(18, 10), textcoords="offset points", fontsize=8, color="white", weight="bold", zorder=12,
                        bbox=dict(boxstyle="round,pad=0.25", fc=PALETTE["panel"], ec=PALETTE["ice"], lw=1.0, alpha=0.92),
                        arrowprops=dict(arrowstyle="-", color=PALETTE["ice"], lw=1.0))
    pts, recs = out["events"]
    seen = set()
    for (x, y), r in zip(pts, recs):
        mk, col, lab = EVENT_STYLE[r[1]]
        kw = dict(edgecolors="white", linewidths=0.6) if mk not in ("x",) else dict(linewidths=1.0)
        ax.scatter([x], [y], marker=mk, s=90 if r[1] == "final_stop" else 16, c=col, zorder=8 if r[1] != "spurious_restart" else 7, **kw)
        seen.add(r[1])
    return seen


def draw_network_runout(ax, out, lw=1.5):
    """Whole-network runout, same palette as the main channel (drawn thinner, over the main-channel tract so that
    both stay readable). Final stops that are not of the main channel have their own marker.
    Returns the set of event keys drawn."""
    from matplotlib.collections import LineCollection
    net = out.get("network")
    if not net or not net["lines"]:
        return set()
    segs = [ln[:, :2] for ln in net["lines"]]
    cols = [PHASE_COLORS.get(rec[4], "#ffffff") for rec in net["lrec"]]
    lws = [_phase_lw(rec[4], lw) for rec in net["lrec"]]
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=lws, zorder=6.5, capstyle="round"))
    present = set()
    for (x, y), r in zip(net["ev_pts"], net["ev_rec"]):
        if r[1] in ("stop", "spurious_restart"):
            continue
        mk, col, lab = EVENT_STYLE[r[1]]
        big = r[1].startswith("final_stop")
        ax.scatter([x], [y], marker=mk, s=80 if big else 14, c=col, edgecolors="white", linewidths=0.6, zorder=8.5 if big else 7.5)
        present.add(r[1])
    return present


def side_legend(ax, classes=False, runout=None, network=None, msf=False):
    """One legend OUTSIDE the map (right of the axes): channel classes, runout tract colours and event markers."""
    h = []

    def head(t):
        h.append(Line2D([], [], color="none", label=t))
    if classes:
        head("Channel classes")
        h += [Line2D([0], [0], color=CLASS_COLORS[k], lw=3, label=CLASS_NAMES[k].capitalize()) for k in (2, 1, 3, 4)]
    if runout is not None or network is not None:
        head("Runout (main channel + whole network)")
        h += [Line2D([0], [0], color=PHASE_COLORS[k], lw=3, label=PHASE_LABELS[k]) for k in (2, 3, 4, 5, 1)]
        ev = set(runout or ()) | set(network or ())
        for k in ("initiation", "restart", "spurious_restart", "stop", "final_stop", "final_stop_lat_on_main", "final_stop_lateral"):
            if k in ev or k == "stop":
                mk, col, lab = EVENT_STYLE[k]
                h.append(Line2D([0], [0], marker=mk, color="none", markerfacecolor=col, markeredgecolor="white" if mk != "x" else col,
                                markersize=7, label=lab))
    if msf:
        head("Other")
        h.append(Line2D([0], [0], marker="o", color="none", markerfacecolor="#ffd166", markeredgecolor="k", markersize=6, label="MSF initiation point"))
    if not h:
        return None
    leg = ax.legend(handles=h, loc="upper left", bbox_to_anchor=(1.015, 1.0), borderaxespad=0.0, fontsize=7, frameon=True,
                    facecolor=PALETTE["panel"], edgecolor=PALETTE["muted"], labelcolor=PALETTE["ink"], handlelength=1.6)
    for t, hd in zip(leg.get_texts(), h):
        if hd.get_label() in ("Channel classes", "Runout (main channel + whole network)", "Other"):
            t.set_fontweight("bold"); t.set_color(PALETTE["ice"])
    return leg


def cum_dist_3d(x, y, z):
    """Cumulative 3-D (slope) distance along a profile."""
    return np.r_[0.0, np.cumsum(np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2 + np.diff(z) ** 2))]


def profile_axes(ax, out, basin=1, compact=False, show3d=False):
    """Elevation profile of one basin's main channel, coloured by class, with runout events.
    show3d overlays the same profile against the 3-D (slope) distance as a dashed line."""
    rows = [r for r in out["profiles"] if r[0] == basin]
    ax.set_facecolor(PALETTE["panel"])
    if not rows:
        return False
    x = np.array([r[2] for r in rows]); y = np.array([r[3] for r in rows])
    d = np.array([r[12] for r in rows])
    z = np.array([r[4] for r in rows])
    cl = np.array([r[5] for r in rows])
    ev = [r[7] for r in rows]
    d3 = cum_dist_3d(x, y, z)
    ms = 1.5 if compact else 3
    if show3d:
        ax.plot(d3, z, color="#ffd166", lw=0.9 if compact else 1.2, ls="--", zorder=2.5, label="3-D distance")
    for k in (1, 2, 3, 4):
        m = cl == k
        ax.scatter(d[m], z[m], s=ms, c=CLASS_COLORS[k], zorder=3, label=CLASS_NAMES[k].capitalize())
    ax.plot(d, z, color=PALETTE["muted"], lw=0.5, zorder=2, label="2-D distance (map)" if show3d else None)
    for i, e in enumerate(ev):
        if e:
            mk, col, lab = EVENT_STYLE[e]
            kw = dict(edgecolors="white", linewidths=0.4) if mk != "x" else dict(linewidths=0.9)
            big = e == "final_stop"
            ax.scatter([d[i]], [z[i]], marker=mk, s=(40 if compact else 70) if big else (8 if compact else 18), c=col, zorder=6, label=lab, **kw)
            if show3d and big:
                ax.scatter([d3[i]], [z[i]], marker=mk, s=(40 if compact else 70), facecolors="none", edgecolors="#ffd166", linewidths=1.2, zorder=6)
    if not compact:
        h, l = ax.get_legend_handles_labels()
        u = dict(zip(l, h))
        ax.legend(u.values(), u.keys(), fontsize=7, facecolor=PALETTE["panel"], edgecolor=PALETTE["muted"], labelcolor=PALETTE["ink"], ncol=2)
        ax.set_xlabel("Distance from head (m)", color=PALETTE["ink"])
        ax.set_ylabel("Elevation (m a.s.l.)", color=PALETTE["ink"])
    ax.tick_params(colors=PALETTE["muted"], labelsize=6 if compact else 9)
    for sp in ax.spines.values():
        sp.set_color(PALETTE["muted"])
    ax.grid(color="#274156", lw=0.4)
    info = next((q for q in out.get("summary", []) if q.get("basin") == basin), None)
    extra = ""
    if info:
        extra = f" · {info['area_km2']:.2f} km² · {d[-1]:.0f} m" + (f" (3-D {d3[-1]:.0f} m)" if show3d else "")
    ax.set_title((f"Basin {basin}" if compact else f"Main channel profile - basin {basin}") + extra, color=PALETTE["ink"],
                 fontsize=7.5 if compact else 10)
    return True


def profile_figure(fig, out, basin=1, factor=0.4, show3d=False):
    fig.patch.set_facecolor(PALETTE["bg"])
    profile_axes(fig.add_subplot(111), out, basin, show3d=show3d)


def profile_matrix(fig, out, ncols=3, show3d=False):
    """Grid of compact profiles, one panel per basin (sorted by basin id)."""
    basins = sorted({r[0] for r in out["profiles"]})
    fig.patch.set_facecolor(PALETTE["bg"])
    if not basins:
        return
    n = len(basins)
    ncols = max(1, min(ncols, n))
    nrows = -(-n // ncols)
    for i, b in enumerate(basins):
        ax = fig.add_subplot(nrows, ncols, i + 1)
        profile_axes(ax, out, b, compact=True, show3d=show3d)
        if i == 0:
            h, l = ax.get_legend_handles_labels()
            u = dict(zip(l, h))
            fig.legend(u.values(), u.keys(), loc="lower center", ncol=len(u), fontsize=7, facecolor=PALETTE["panel"],
                       edgecolor=PALETTE["muted"], labelcolor=PALETTE["ink"])
    fig.tight_layout(rect=(0, 0.05, 1, 1))
