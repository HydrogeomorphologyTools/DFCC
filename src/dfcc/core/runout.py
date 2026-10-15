"""Main-channel selection and morphometric runout (stop distance) of potential debris flows.

Energy-dissipation rule of Procedura-DF (Excel / Matlab 'Procedura_Runout'): walking downstream
along the classified profile,
    L  = cumulated elevation lost on points of class 1,2 (propagation / initiation)
    K  = cumulated distance travelled on points of class 3,4 (slowing / stop zones)
and the flow stops at the first point where  K > 0.4 * L.
After a stop the flow may restart at the next initiation point (class 2) with L, K reset.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from ._jit import njit
from .hydro import D1, D2

ENERGY_FACTOR = 0.4
PH_NONE, PH_PRE, PH_FLOW, PH_STOP, PH_BETWEEN, PH_AFTER = 0, 1, 2, 3, 4, 5

# DF_YN states (Matlab application): 1 no flow, 2 stop, 3 flow
NO_FLOW, STOP, FLOW = 1, 2, 3


# ---------------------------------------------------------------- profile runout
@dataclass
class RunoutResult:
    state: np.ndarray          # DF_YN per point (1/2/3)
    event: np.ndarray          # '' | 'initiation' | 'stop' | 'restart' | 'spurious_restart' | 'final_stop'
    L: np.ndarray
    K: np.ndarray
    dist: np.ndarray           # segment length ending at each point
    drop: np.ndarray
    cum_dist: np.ndarray
    phase: np.ndarray | None = None
    stops: list = field(default_factory=list)
    final_stop: int | None = None


def profile_runout(cls, z, x, y, factor=ENERGY_FACTOR, min_restart_len=30.0, start_at_head=False):
    """Apply the energy rule on a downstream-ordered point profile.

    cls: class code (1 propagation, 2 initiation, 3 slowing, 4 stop zone) per point
    z, x, y: elevation and coordinates. Returns RunoutResult.
    A restart that is extinguished within `min_restart_len` metres is labelled spurious; the final
    (definitive) stop is the last stop not followed by a non-spurious restart."""
    n = len(cls)
    cls = np.asarray(cls)
    z = np.asarray(z, float)
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    dist = np.zeros(n)
    drop = np.zeros(n)
    dist[1:] = np.hypot(np.diff(x), np.diff(y))
    drop[1:] = z[:-1] - z[1:]
    cum = np.cumsum(dist)
    state = np.full(n, NO_FLOW, np.int8)
    event = np.array([""] * n, dtype=object)
    L = np.zeros(n)
    K = np.zeros(n)
    flowing = False
    Lc = Kc = 0.0
    stops = []
    starts = []                       # (point index, kind) of each flow start
    for i in range(n):
        if not flowing:
            if cls[i] == 2 or (start_at_head and not starts and i == 0):
                flowing = True
                Lc = float(drop[i])   # Excel: the restart cell inherits the drop into it
                Kc = 0.0
                kind = "initiation" if not starts else "restart"
                event[i] = kind
                starts.append((i, kind))
                state[i] = FLOW
                L[i], K[i] = Lc, Kc
            continue
        if cls[i] < 3:
            Lc += drop[i]
        else:
            Kc += dist[i]
        L[i], K[i] = Lc, Kc
        if Kc > factor * Lc:
            state[i] = STOP
            event[i] = "stop"
            stops.append(i)
            flowing = False
        else:
            state[i] = FLOW
    # restarts: classify spurious / valid, final stop
    starts_idx = [s for s, _ in starts]
    for si, (s, kind) in enumerate(starts):
        if kind == "restart":
            nxt_stop = next((p for p in stops if p > s), None)
            life = (cum[nxt_stop] if nxt_stop is not None else cum[-1]) - cum[s]
            if life < min_restart_len:
                event[s] = "spurious_restart"
    final = None
    for p in stops:
        later = [s for s, k in starts if s > p and event[s] == "restart"]
        if not later:
            final = p
            break
    if final is not None:
        event[final] = "final_stop"
    phase = np.zeros(n, np.int8)
    valid = [s for s, _ in starts if event[s] == 'restart']
    first = starts[0][0] if starts else n
    for i in range(n):
        if state[i] == FLOW:
            phase[i] = PH_FLOW
        elif state[i] == STOP:
            phase[i] = PH_STOP
        elif i < first:
            phase[i] = PH_PRE
        else:
            phase[i] = PH_BETWEEN if any(v > i for v in valid) else PH_AFTER
    return RunoutResult(state, event, L, K, dist, drop, cum, phase, stops, final)


# ------------------------------------------------------------ main-channel search
@njit
def _topo_and_longest(stream, p, deg, cell):
    ny, nx = stream.shape
    order = np.empty(ny * nx, np.int64)
    qt = 0
    for r in range(ny):
        for c in range(nx):
            if stream[r, c] and deg[r, c] == 0:
                order[qt] = r * nx + c
                qt += 1
    up_len = np.zeros((ny, nx), np.float64)
    best_up = np.full((ny, nx), -1, np.int64)
    qh = 0
    while qh < qt:
        cur = order[qh]
        qh += 1
        r = cur // nx
        c = cur % nx
        k = p[r, c]
        if k >= 1 and k <= 8:
            rr = r + D2[k]
            cc = c + D1[k]
            if rr >= 0 and cc >= 0 and rr < ny and cc < nx and stream[rr, cc]:
                step = cell * (1.4142135623730951 if (k % 2 == 0) else 1.0)
                v = up_len[r, c] + step
                if v > up_len[rr, cc] or best_up[rr, cc] < 0:
                    up_len[rr, cc] = v
                    best_up[rr, cc] = cur
                deg[rr, cc] -= 1
                if deg[rr, cc] == 0:
                    order[qt] = rr * nx + cc
                    qt += 1
    return order[:qt], up_len, best_up


def longest_paths(stream, p, cell):
    """For every stream cell: length of the longest upstream flow path and the inflow cell that gives it."""
    from .network import _indeg_stream
    stream = np.ascontiguousarray(stream, dtype=np.bool_)
    p = np.ascontiguousarray(p, dtype=np.int16)
    deg = _indeg_stream(stream, p)
    return _topo_and_longest(stream, p, deg, float(cell))


def main_channel_from_outlet(outlet_rc, best_up, shape):
    """Cells (row, col) from headwater to the outlet along the longest upstream path."""
    ny, nx = shape
    cells = []
    cur = outlet_rc[0] * nx + outlet_rc[1]
    while cur >= 0:
        cells.append(cur)
        cur = best_up[cur // nx, cur % nx]
    cells = np.array(cells[::-1], dtype=np.int64)
    return cells // nx, cells % nx


def downstream_path(start_rc, p, stream, shape):
    ny, nx = shape
    r, c = start_rc
    out = [(r, c)]
    while True:
        k = p[r, c]
        if not (1 <= k <= 8):
            break
        r, c = r + D2[k], c + D1[k]
        if r < 0 or c < 0 or r >= ny or c >= nx or not stream[r, c]:
            break
        out.append((r, c))
    a = np.array(out)
    return a[:, 0], a[:, 1]


@njit
def _label_basins(stream_or_all, p, order_ok, seeds_r, seeds_c, nseed):
    ny, nx = p.shape
    lab = np.zeros((ny, nx), np.int32)
    for i in range(nseed):
        lab[seeds_r[i], seeds_c[i]] = i + 1
    return lab


def basin_labels(p, outlets_rc):
    """Label every cell draining to one of the outlets (1..n). Outlets may be nested: the smaller
    (upstream) basin keeps its cells only if listed first; here each cell goes to the nearest
    downstream outlet, i.e. basins are non-overlapping sub-basins."""
    from .hydro import _indegree
    p = np.ascontiguousarray(p, dtype=np.int16)
    ny, nx = p.shape
    deg = _indegree(p)
    rr = np.array([o[0] for o in outlets_rc], dtype=np.int64)
    cc = np.array([o[1] for o in outlets_rc], dtype=np.int64)
    return _label_up(p, deg, rr, cc)


@njit
def _label_up(p, deg, rr, cc):
    ny, nx = p.shape
    lab = np.zeros((ny, nx), np.int32)
    for i in range(rr.size):
        lab[rr[i], cc[i]] = i + 1
    # topological order from sources
    order = np.empty(ny * nx, np.int64)
    qt = 0
    for r in range(ny):
        for c in range(nx):
            if p[r, c] != -32768 and deg[r, c] == 0:
                order[qt] = r * nx + c
                qt += 1
    qh = 0
    while qh < qt:
        cur = order[qh]
        qh += 1
        r = cur // nx
        c = cur % nx
        k = p[r, c]
        if k >= 1 and k <= 8:
            r2 = r + D2[k]
            c2 = c + D1[k]
            if r2 >= 0 and c2 >= 0 and r2 < ny and c2 < nx and p[r2, c2] != -32768:
                deg[r2, c2] -= 1
                if deg[r2, c2] == 0:
                    order[qt] = r2 * nx + c2
                    qt += 1
    for j in range(qt - 1, -1, -1):
        cur = order[j]
        r = cur // nx
        c = cur % nx
        if lab[r, c] == 0:
            k = p[r, c]
            if k >= 1 and k <= 8:
                r2 = r + D2[k]
                c2 = c + D1[k]
                if r2 >= 0 and c2 >= 0 and r2 < ny and c2 < nx:
                    lab[r, c] = lab[r2, c2]
    return lab


@njit
def _best_up_area(stream, p, ad8):
    ny, nx = stream.shape
    best = np.full((ny, nx), -1, np.int64)
    for r in range(ny):
        for c in range(nx):
            if not stream[r, c]:
                continue
            ba = -1.0
            for k in range(1, 9):
                r2 = r - D2[k]
                c2 = c - D1[k]
                if r2 < 0 or c2 < 0 or r2 >= ny or c2 >= nx or not stream[r2, c2]:
                    continue
                kk = p[r2, c2]
                if kk >= 1 and kk <= 8 and r2 + D2[kk] == r and c2 + D1[kk] == c:
                    if ad8[r2, c2] > ba:
                        ba = ad8[r2, c2]
                        best[r, c] = r2 * nx + c2
    return best


def largest_area_upstream(stream, p, ad8):
    """For every stream cell: the inflowing stream cell with the largest contributing area (-1 at heads)."""
    return _best_up_area(np.ascontiguousarray(stream, dtype=np.bool_), np.ascontiguousarray(p, dtype=np.int16),
                         np.ascontiguousarray(ad8, dtype=np.float32))


# ------------------------------------------------------------ whole-network runout
EV_NONE, EV_INIT, EV_RESTART, EV_STOP = 0, 1, 2, 3


@njit
def _network_kernel(dom, p, cls, fel, area, cell, factor, main):
    """Topological (upstream -> downstream) pass of the energy rule over every cell of `dom`.
    Where several flowing branches merge, the one with the largest energy margin
    (factor*L - K) is propagated (envelope, no summing)."""
    ny, nx = p.shape
    deg = np.zeros((ny, nx), np.int32)
    for r in range(ny):
        for c in range(nx):
            if dom[r, c]:
                k = p[r, c]
                if 1 <= k <= 8:
                    rr, cc = r + D2[k], c + D1[k]
                    if 0 <= rr < ny and 0 <= cc < nx and dom[rr, cc]:
                        deg[rr, cc] += 1
    state = np.ones((ny, nx), np.int8)
    ev = np.zeros((ny, nx), np.int8)
    L = np.zeros((ny, nx))
    K = np.zeros((ny, nx))
    cand_m = np.full((ny, nx), -np.inf)
    cand_L = np.zeros((ny, nx)); cand_K = np.zeros((ny, nx))
    cand_dr = np.zeros((ny, nx)); cand_ds = np.zeros((ny, nx))
    big_a = np.full((ny, nx), -1.0); big_dr = np.zeros((ny, nx))
    ever_in = np.zeros((ny, nx), np.bool_)
    lat = np.zeros((ny, nx), np.bool_)          # state currently carried comes from a lateral branch
    ever_arr = np.zeros((ny, nx), np.bool_)
    cand_lat = np.zeros((ny, nx), np.bool_)
    queue = np.empty(ny * nx, np.int64)
    qh = 0; qt = 0
    for r in range(ny):
        for c in range(nx):
            if dom[r, c] and deg[r, c] == 0:
                queue[qt] = r * nx + c; qt += 1
    while qh < qt:
        idx = queue[qh]; qh += 1
        r = idx // nx; c = idx % nx
        flowing = False
        if cand_m[r, c] > -np.inf:
            Lc = cand_L[r, c]; Kc = cand_K[r, c]
            lat[r, c] = cand_lat[r, c]
            if cls[r, c] < 3:
                Lc += cand_dr[r, c]
            else:
                Kc += cand_ds[r, c]
            L[r, c] = Lc; K[r, c] = Kc
            if Kc > factor * Lc:
                state[r, c] = 2; ev[r, c] = EV_STOP
            else:
                state[r, c] = 3; flowing = True
        elif cls[r, c] == 2:
            Lc = big_dr[r, c] if big_a[r, c] >= 0 else 0.0
            L[r, c] = Lc; K[r, c] = 0.0
            state[r, c] = 3; flowing = True
            ev[r, c] = EV_RESTART if ever_in[r, c] else EV_INIT
            lat[r, c] = not main[r, c]
        ever = ever_in[r, c] or state[r, c] != 1
        ever_arr[r, c] = ever
        k = p[r, c]
        if 1 <= k <= 8:
            rr = r + D2[k]; cc = c + D1[k]
            if 0 <= rr < ny and 0 <= cc < nx and dom[rr, cc]:
                dr = fel[r, c] - fel[rr, cc]
                ds = cell * (1.4142135623730951 if (D1[k] != 0 and D2[k] != 0) else 1.0)
                if flowing:
                    m = factor * L[r, c] - K[r, c]
                    if m > cand_m[rr, cc]:
                        cand_m[rr, cc] = m
                        cand_L[rr, cc] = L[r, c]; cand_K[rr, cc] = K[r, c]
                        cand_dr[rr, cc] = dr; cand_ds[rr, cc] = ds
                        # lateral-driven if the winning branch is a lateral (or already lateral-driven)
                        cand_lat[rr, cc] = (not main[r, c]) or lat[r, c]
                if area[r, c] > big_a[rr, cc]:
                    big_a[rr, cc] = area[r, c]; big_dr[rr, cc] = dr
                if ever:
                    ever_in[rr, cc] = True
                deg[rr, cc] -= 1
                if deg[rr, cc] == 0:
                    queue[qt] = rr * nx + cc; qt += 1
    return state, ev, L, K, lat, ever_arr, queue[:qt].copy()


def _recv(p, r, c, shape):
    k = p[r, c]
    if not (1 <= k <= 8):
        return None
    rr, cc = r + D2[k], c + D1[k]
    if rr < 0 or cc < 0 or rr >= shape[0] or cc >= shape[1]:
        return None
    return rr, cc


@njit
def _downstream_flags(order, p, dom, main, state, ev, spur):
    """Reverse topological pass. dn_main[c]: a valid flowing cell exists downstream on main-channel cells
    (restart or re-activation by a tributary); dn_lat[c]: a valid restart exists downstream before the path
    reaches the main channel."""
    ny, nx = p.shape
    dn_main = np.zeros((ny, nx), np.bool_)
    dn_lat = np.zeros((ny, nx), np.bool_)
    for i in range(len(order) - 1, -1, -1):
        r = order[i] // nx; c = order[i] % nx
        k = p[r, c]
        if 1 <= k <= 8:
            rr = r + D2[k]; cc = c + D1[k]
            if 0 <= rr < ny and 0 <= cc < nx and dom[rr, cc]:
                if main[rr, cc]:
                    dn_main[r, c] = (state[rr, cc] == 3 and not spur[rr, cc]) or dn_main[rr, cc]
                else:
                    dn_main[r, c] = False
                if not main[rr, cc]:
                    dn_lat[r, c] = ev[rr, cc] == 2 or dn_lat[rr, cc]
    return dn_main, dn_lat


# tract phases (shared by the main-channel profile and the whole-network runout)
PH_NONE, PH_PRE, PH_FLOW, PH_STOP, PH_BETWEEN, PH_AFTER = 0, 1, 2, 3, 4, 5
PHASE_NAMES = {PH_PRE: "not activated", PH_FLOW: "flow", PH_STOP: "stop", PH_BETWEEN: "stopped, flow resumes below",
               PH_AFTER: "after final stop"}


def network_runout(dom, p, cls, fel, ad8, cell, factor=ENERGY_FACTOR, min_restart_len=30.0, main=None):
    """Energy rule on the whole network `dom` (bool grid). Returns dict with per-cell grids
    state (1 no flow / 2 stop / 3 flow), event (0 none, 1 initiation, 2 restart, 3 stop, 4 final stop,
    9 spurious restart), L, K, margin = factor*L - K, lateral (state carried comes from a lateral) and
    phase (tract colouring, see PHASE_NAMES).
    Final stop: on a main-channel cell, no valid flow (restart or re-activation by a tributary) occurs
    downstream on the main channel; on a lateral, no valid restart occurs before the path joins the main channel."""
    dom = np.ascontiguousarray(dom, np.bool_)
    p16 = np.ascontiguousarray(p, np.int16)
    main_ = np.ascontiguousarray(main if main is not None else dom, np.bool_)
    state, ev, L, K, lat, ever, order = _network_kernel(dom, p16, np.ascontiguousarray(cls, np.int16),
                                      np.ascontiguousarray(fel, np.float64),
                                      np.ascontiguousarray(ad8, np.float64), float(cell), float(factor), main_)
    shape = dom.shape
    spur = np.zeros(shape, bool)
    for r, c in zip(*np.where(ev == 2)):             # spurious restarts: flow that dies within min_restart_len
        cur = (int(r), int(c)); life = 0.0; walked = [cur]
        while True:
            nx_ = _recv(p16, cur[0], cur[1], shape)
            if nx_ is None or not dom[nx_]:
                break
            life += cell * (1.4142135623730951 if (nx_[0] != cur[0] and nx_[1] != cur[1]) else 1.0)
            cur = nx_
            if state[cur] != 3 or life >= min_restart_len:
                break
            walked.append(cur)
        if life < min_restart_len:
            ev[r, c] = 9
            for w in walked:
                spur[w] = True
    dn_main, dn_lat = _downstream_flags(order, p16, dom, main_, state, ev, spur)
    cont = np.where(main_, dn_main, dn_lat)           # flow resumes downstream on the reference path
    ev = np.where((ev == 3) & ~cont, 4, ev).astype(ev.dtype)
    phase = np.zeros(shape, np.int8)
    phase[dom & (state == 3)] = PH_FLOW
    phase[dom & (state == 2)] = PH_STOP
    nf = dom & (state == 1)
    phase[nf & ~ever] = PH_PRE
    phase[nf & ever & cont] = PH_BETWEEN
    phase[nf & ever & ~cont] = PH_AFTER
    return dict(state=state, event=ev, L=L, K=K, lateral=lat, main=main_, phase=phase,
                margin=np.where(state != 1, factor * L - K, 0.0))
