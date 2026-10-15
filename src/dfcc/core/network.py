"""Stream-to-feature + 3-D interpolation (ArcGIS StreamToFeature / InterpolateShape equivalent).

Geometry rules reproduced from the reference output (Reticolo3D.shp):
* arcs run source/junction -> next junction/outlet following the D8 directions;
* vertices only where the direction changes (NO_SIMPLIFY of Spatial Analyst keeps cell-edge
  half-steps: a headwater arc starts half a cell upstream of the source cell centre, an outlet arc
  ends half a cell downstream of the last cell centre);
* every straight run is densified in floor(length/cellsize)+1 equal pieces;
* Z is bilinear-interpolated on the (filled) DTM.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import numpy as np
from ._jit import njit
from .hydro import D1, D2


@njit
def _trace(stream, p, deg, order_r, order_c, n_start, path, ptr, kind):
    ny, nx = stream.shape
    npth = 0
    narc = 0
    ptr[0] = 0
    for s in range(n_start):
        r = order_r[s]
        c = order_c[s]
        cr = r
        cc = c
        path[npth] = r * nx + c
        npth += 1
        end_kind = 0           # 0 junction end, 1 outlet end
        while True:
            k = p[cr, cc]
            nr = cr + D2[k] if (k >= 1 and k <= 8) else -1
            nc = cc + D1[k] if (k >= 1 and k <= 8) else -1
            if nr < 0 or nc < 0 or nr >= ny or nc >= nx or not stream[nr, nc]:
                end_kind = 1
                break
            path[npth] = nr * nx + nc
            npth += 1
            cr = nr
            cc = nc
            if deg[cr, cc] != 1:
                break
        narc += 1
        ptr[narc] = npth
        kind[narc - 1] = end_kind
    return narc, npth


@njit
def _indeg_stream(stream, p):
    ny, nx = stream.shape
    deg = np.zeros((ny, nx), np.int32)
    for r in range(ny):
        for c in range(nx):
            if stream[r, c]:
                k = p[r, c]
                if k >= 1 and k <= 8:
                    rr = r + D2[k]
                    cc = c + D1[k]
                    if rr >= 0 and cc >= 0 and rr < ny and cc < nx and stream[rr, cc]:
                        deg[rr, cc] += 1
    return deg


@dataclass
class Arcs:
    cells: list            # per arc: int array of flat cell indices (row*nx+col) along the path
    end_kind: np.ndarray   # 1 if the arc ends at an outlet (half-cell extension)
    start_is_source: np.ndarray
    deg: np.ndarray
    shape: tuple
    node_xy: dict = field(default_factory=dict)


def extract_arcs(src, p):
    stream = np.ascontiguousarray(src == 1)
    p = np.ascontiguousarray(p, dtype=np.int16)
    ny, nx = stream.shape
    deg = _indeg_stream(stream, p)
    rr, cc = np.nonzero(stream & (deg != 1))          # row-major order
    n = rr.size
    path = np.empty(int(stream.sum()) + n + 8, np.int64)   # junction cells repeat once per arc
    ptr = np.zeros(n + 1, np.int64)
    kind = np.zeros(n, np.int8)
    # a junction cell starts one arc, and ends >= 2 arcs, so path <= stream cells + arcs
    narc, npth = _trace(stream, p, deg, rr.astype(np.int64), cc.astype(np.int64), n, path, ptr, kind)
    cells = [path[ptr[i]:ptr[i + 1]].copy() for i in range(narc)]
    is_src = np.array([deg[rr[i], cc[i]] == 0 for i in range(narc)])
    return Arcs(cells, kind[:narc].copy(), is_src, deg, (ny, nx))


def _bilinear(fel, nodata, col, row):
    ny, nx = fel.shape
    c0 = np.floor(col).astype(np.int64)
    r0 = np.floor(row).astype(np.int64)
    fc = col - c0
    fr = row - r0
    num = np.zeros(col.shape)
    den = np.zeros(col.shape)
    for dr, dc, w in ((0, 0, (1 - fc) * (1 - fr)), (0, 1, fc * (1 - fr)),
                      (1, 0, (1 - fc) * fr), (1, 1, fc * fr)):
        r = np.clip(r0 + dr, 0, ny - 1)
        c = np.clip(c0 + dc, 0, nx - 1)
        z = fel[r, c].astype(np.float64)
        ok = (z != nodata) & np.isfinite(z) & (w > 0)
        num += np.where(ok, z * w, 0.0)
        den += np.where(ok, w, 0.0)
    out = np.full(col.shape, np.nan)
    good = den > 0
    out[good] = num[good] / den[good]
    return out


def arc_vertices_cell_units(cells, ends_at_outlet, starts_at_source, p, nx):
    """Corner vertices (col,row float, cell-centre = integer) of one arc before densification."""
    rc = np.stack([cells // nx, cells % nx], axis=1).astype(np.float64)   # (row,col)
    pts = [rc[i] for i in range(len(rc))]
    if starts_at_source or len(rc) == 1:
        k = p[int(rc[0, 0]), int(rc[0, 1])]
        if 1 <= k <= 8:
            first = np.array([rc[0, 0] - 0.5 * D2[k], rc[0, 1] - 0.5 * D1[k]])
            pts.insert(0, first)
    if ends_at_outlet:
        k = p[int(rc[-1, 0]), int(rc[-1, 1])]
        if 1 <= k <= 8:
            pts.append(np.array([rc[-1, 0] + 0.5 * D2[k], rc[-1, 1] + 0.5 * D1[k]]))
    P = np.array(pts)
    if len(P) <= 2:
        return P
    d = np.diff(P, axis=0)
    keep = [0]
    for i in range(1, len(P) - 1):
        if not np.allclose(np.sign(d[i - 1]), np.sign(d[i])):   # direction change
            keep.append(i)
    keep.append(len(P) - 1)
    return P[keep]


def densify(P, cell, sample_dist):
    """Equal-piece densification of each straight run: floor(len/sample)+1 pieces,
    runs not longer than the sample distance are left untouched (ArcGIS InterpolateShape)."""
    out = [P[0]]
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        q = float(np.hypot(*(b - a))) * cell / sample_dist
        n = 1 if q <= 1.0 + 1e-9 else int(math.floor(q + 1e-9)) + 1
        t = np.arange(1, n + 1) / n
        out.extend(a + (b - a) * ti for ti in t)
    return np.array(out)


def build_network(src, p, fel, nodata, transform, cell, sample_dist=None):
    """Return list of arcs: dict(xyz=(N,3), cells=..., from_node, to_node, arcid)."""
    x0, y0 = transform
    sample_dist = sample_dist or cell
    arcs = extract_arcs(src, p)
    ny, nx = arcs.shape
    pi = np.asarray(p)
    # node ids: row-major order of all node positions (cell centres; outlets at their extended end)
    node_keys = []
    arc_nodes = []
    for i, cells in enumerate(arcs.cells):
        r0, c0 = divmod(int(cells[0]), nx)
        r1, c1 = divmod(int(cells[-1]), nx)
        if arcs.start_is_source[i]:
            k = pi[r0, c0]
            sk = (r0 - 0.5 * D2[k], c0 - 0.5 * D1[k]) if 1 <= k <= 8 else (r0, c0)
        else:
            sk = (r0, c0)
        if arcs.end_kind[i]:
            k = pi[r1, c1]
            ek = (r1 + 0.5 * D2[k], c1 + 0.5 * D1[k]) if 1 <= k <= 8 else (r1, c1)
        else:
            ek = (r1, c1)
        arc_nodes.append((sk, ek))
        node_keys.extend([sk, ek])
    # sources/outlets sit on the cell they belong to for numbering purposes
    def nkey(pt):
        return (math.floor(pt[0] + 0.5), math.floor(pt[1] + 0.5), pt)
    uniq = sorted({k for k in node_keys}, key=lambda t: (math.floor(t[0] + 0.5), math.floor(t[1] + 0.5), t))
    nid = {k: i + 1 for i, k in enumerate(uniq)}
    out = []
    for i, cells in enumerate(arcs.cells):
        P = arc_vertices_cell_units(cells, bool(arcs.end_kind[i]), bool(arcs.start_is_source[i]), pi, nx)
        D = densify(P, cell, sample_dist)
        col = D[:, 1]
        row = D[:, 0]
        z = _bilinear(fel, nodata, col, row)
        x = x0 + (col + 0.5) * cell
        y = y0 - (row + 0.5) * cell
        sk, ek = arc_nodes[i]
        out.append(dict(arcid=i + 1, xyz=np.column_stack([x, y, z]), cells=cells,
                        from_node=nid[sk], to_node=nid[ek],
                        end_outlet=bool(arcs.end_kind[i])))
    return out, arcs
