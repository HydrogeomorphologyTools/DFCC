"""Initiation 'hot-spot' points: one snapped point at the head of every high-density area,
pruned so that only the highest of several points aligned on the same flow path is kept
(to optimise runs of e.g. MSF / Flow-R style models)."""
from __future__ import annotations
import numpy as np
from ._jit import njit
from .hydro import D1, D2


@njit
def label_components(mask):
    """8-connected component labelling (numba, no scipy needed)."""
    ny, nx = mask.shape
    lab = np.zeros((ny, nx), np.int32)
    stack = np.empty(ny * nx, np.int64)
    n = 0
    for r in range(ny):
        for c in range(nx):
            if mask[r, c] and lab[r, c] == 0:
                n += 1
                lab[r, c] = n
                sp = 0
                stack[sp] = r * nx + c
                sp += 1
                while sp > 0:
                    sp -= 1
                    cur = stack[sp]
                    cr = cur // nx
                    cc = cur % nx
                    for dr in range(-1, 2):
                        for dc in range(-1, 2):
                            rr = cr + dr
                            c2 = cc + dc
                            if rr >= 0 and c2 >= 0 and rr < ny and c2 < nx and mask[rr, c2] and lab[rr, c2] == 0:
                                lab[rr, c2] = n
                                stack[sp] = rr * nx + c2
                                sp += 1
    return lab, n


def _inflow_neighbours(r, c, p, shape):
    ny, nx = shape
    res = []
    for k in range(1, 9):
        r2, c2 = r - D2[k], c - D1[k]
        if 0 <= r2 < ny and 0 <= c2 < nx:
            kk = p[r2, c2]
            if 1 <= kk <= 8 and r2 + D2[kk] == r and c2 + D1[kk] == c:
                res.append((r2, c2))
    return res


def find_hotspots(high, src, p, ad8, fel, density, cell, snap_m=50.0, prune=True, max_down_m=None):
    """Return list of dicts (patch id, row, col, z, area_km2, dens, keep flag, dropped_by)."""
    ny, nx = high.shape
    lab, n = label_components(np.ascontiguousarray(high))
    stream = src == 1
    rad = int(np.ceil(snap_m / cell))
    pts = []
    for pid in range(1, n + 1):
        rr, cc = np.nonzero(lab == pid)
        r0, r1 = max(rr.min() - rad, 0), min(rr.max() + rad + 1, ny)
        c0, c1 = max(cc.min() - rad, 0), min(cc.max() + rad + 1, nx)
        sub_patch = lab[r0:r1, c0:c1] == pid
        sub_stream = stream[r0:r1, c0:c1]
        inside = sub_patch & sub_stream
        if not inside.any():
            # stream cells within snap distance of the patch
            pr, pc = np.nonzero(sub_patch)
            sr, sc = np.nonzero(sub_stream)
            if sr.size == 0:
                continue
            # chunked nearest distance (patches are small)
            d2 = ((sr[:, None] - pr[None, :]) ** 2 + (sc[:, None] - pc[None, :]) ** 2).min(axis=1)
            near = d2 * cell * cell <= snap_m * snap_m
            if not near.any():
                continue
            cand = {(int(sr[i]) + r0, int(sc[i]) + c0) for i in np.nonzero(near)[0]}
            snapped = True
        else:
            ir, ic = np.nonzero(inside)
            cand = {(int(a) + r0, int(b) + c0) for a, b in zip(ir, ic)}
            snapped = False
        remaining = set(cand)
        while remaining:
            # outlet of the local network piece = candidate with the largest contributing area
            out = max(remaining, key=lambda t: ad8[t])
            comp = {out}
            frontier = [out]
            head = out
            while frontier:                              # collect all upstream candidate cells
                cur = frontier.pop()
                for nb in _inflow_neighbours(cur[0], cur[1], p, (ny, nx)):
                    if nb in remaining and nb not in comp:
                        comp.add(nb)
                        frontier.append(nb)
            cur = out                                    # main stem: follow the largest inflow
            while True:
                ins = [nb for nb in _inflow_neighbours(cur[0], cur[1], p, (ny, nx)) if nb in comp]
                if not ins:
                    break
                cur = max(ins, key=lambda t: ad8[t])
            head = cur
            remaining -= comp
            pts.append(dict(patch=pid, row=head[0], col=head[1], z=float(fel[head]),
                            area_km2=float(ad8[head]) * cell * cell / 1e6,
                            dens=float(density[head]), snapped=snapped, keep=True, dropped_by=0))
    for i, d in enumerate(pts):
        d["id"] = i + 1
    if prune:
        order = sorted(pts, key=lambda d: -d["z"])
        covered = {}
        for d in order:
            key = (d["row"], d["col"])
            if key in covered:
                d["keep"] = False
                d["dropped_by"] = covered[key]
                continue
            r, c = key
            length = 0.0
            while True:
                k = p[r, c]
                if not (1 <= k <= 8):
                    break
                r, c = r + D2[k], c + D1[k]
                if r < 0 or c < 0 or r >= ny or c >= nx or not stream[r, c]:
                    break
                length += cell * (1.41421356 if k % 2 == 0 else 1.0)
                if max_down_m is not None and length > max_down_m:
                    break
                covered.setdefault((r, c), d["id"])
    return pts
