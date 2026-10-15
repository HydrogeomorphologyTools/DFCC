# DFCC – method, implementation choices and validation

## 1. Hydrological chain (replica of the ModelBuilder + TauDEM workflow)
1. **PitRemove** (8-neighbour priority-flood; cells next to NoData or on the border drain out) — identical to TauDEM `pitremove` and to ArcGIS `Fill` (no z-limit).
2. **D∞** (`slp`) and **D8** (`p`, `sd8`) TauDEM, including flat resolution.
3. **AreaD8 -nc** (cells) → `ad8`; `sa = sd8^1 · ad8^0.5` (float32 as in the C++ code); **D8FlowPathExtremeUp -nc** (maximum upslope) → `ssa`; **Threshold** `ssa ≥ T` → `src` (network).
4. Raster algebra: `s38 = slp (slp<0.7812)`, `akm2 = ad8·res²/1e6`, `WB = 0.32·akm2^-0.2`; initiation `s38>WB & akm2<20`; slowing `0.0524<s38<0.1405` minus `inDF8`; stop `s38<0.0524` → classified network (1 propagation, 2 initiation, 3 slowing, 4 stop).
5. **Density**: points = centres of the `inDF=1` cells (whole DTM), quartic (Silverman) kernel, 50 m radius, hectares, planar → `InitiationDensity` (points/ha).
6. **High density**: zeros excluded, exact Fisher–Jenks natural breaks with 2 classes on the rest; the upper class = polygons.

## 2. Vector network
Arcs run source/confluence → confluence/outlet; vertices only at direction changes; the headwater arc starts half a cell upstream of the
source-cell centre and the outlet arc ends half a cell downstream; each straight run is densified into `floor(L/cell)+1` equal parts
(no densification if L ≤ cell); Z is bilinear on the filled DTM. `arcid/from_node/to_node` are topologically equivalent to, but not always identical with, ESRI's (internal numbering).

## 3. Runout (part 2)
Procedura‑DF energy rule (Excel/Matlab): going downstream along the profile, `L` = cumulative drop on class 1‑2 points,
`K` = cumulative distance on class 3‑4 points; **stop** at the first point with `K > 0.4·L`. After a stop, at the next class‑2 point the flow
**restarts** (L, K reset). A restart that dies within `min_restart_len` (30 m) is **spurious**.
**Final stop** = last stop not followed by a valid restart (if the flow reaches the outlet there is no final stop).
`DF_YN`: 1 no flow, 2 stop, 3 flow.

*Basin selection* (default): network outlets with area between 1 and 20 km², with **splitting at significant confluences** (both branches ≥ 2 km²;
on Gadria this separates Gadria and Strimm). Alternatives: user pour points (`--pour-points`), min/max area only.

*Main channel* (`--main-branch`):
* `area` (default) – going upstream from the outlet, at every confluence follow the inflow with the **largest contributing area**. This keeps the path in the real hydrological concavity (the geomorphic main channel) instead of cutting into a secondary hollow.
* `longest` – longest upstream flow path (can leave the main concavity in the upper basin).
* `highest` – highest source of the basin, followed downstream by D8 to the outlet.

*Extension past the outlet*: `extend_downstream_m` / `extend_polygon` continue the profile downstream of the basin outlet along the network (D8 path) for the given distance or until the polygon (e.g. catchment + fan) is left, so that stops over a fan can be detected. Do not use a DTM clipped with a 1-cell-wide neck at the outlet: the flow ends there.

## 4. Initiation points for models (MSF, etc.)
For each high-density area: network cells inside the area (or within `snap` m); for each local network piece the path is traced upstream along the
branch with the largest contributing area up to the head → point snapped on the network. Pruning: points are sorted by decreasing elevation and one lying on the
downstream D8 path of a higher kept point is dropped (`keep=0`, `dropped_by` = id of the covering point).

## 5. Validation
See the README table. Known differences: the D∞ angle `ang` differs from the original Windows build in ~860 of 2.7 M cells because of float rounding on exactly diagonal facets (not used by the procedure; `slp` and everything else coincide); `sa`/`ssa` differ in 3 cells by 1 ulp (libm).

## Whole-network runout (optional)

With `whole_network=True` (`--whole-network`) the energy rule is applied to **every channel cell** of the selected basins (plus the optional extension below the outlets), processed in topological order (upstream to downstream). For each cell:

* if at least one upstream neighbour is *flowing*, the state with the **largest energy margin** `0.4·L − K` is inherited (envelope — states are never summed); the cell then adds its own drop `Δz` to `L` (class 1–2) or its distance to `K` (class 3–4) and stops if `K > 0.4·L`;
* if no upstream neighbour is flowing, a class‑2 cell starts a flow (`initiation` if nothing has flowed upstream before, otherwise `restart`; `L` = drop from the largest-area donor, `K` = 0); any other cell is *no flow*;
* a flowing tributary therefore re-activates a stopped trunk;
* a restart extinguished within `min_restart_len` is *spurious*; a stop is *final* when no valid restart occurs anywhere on its downstream D8 path (a tributary may still carry the flow past it).

On a single path with no confluence the result is identical to the main-channel profile rule. Outputs: `Runout_network.shp` (links coloured by class/state with L, K, margin), `Runout_network_events.shp`, and `net_*` columns in `Runout_summary.csv` (cells, flowing cells/length, initiations, restarts, stops, final stops, state and margin at the outlet). Nested sub-basins: the downstream basin includes the flow arriving from the upstream ones.

Final stops are classified by where they occur: on the main channel (own energy), on a lateral, or on the main channel but driven by a lateral (the winning state at the last confluence came from a lateral and no new initiation has reset it). Summary columns `net_final_stops_main` and `net_final_stops_lateral` (lateral + lateral-driven).

## Authors and reference

Stefano Crema, Marco Cavalli, Alessandro Sarretta — CNR GEO, 2026. Method: GIS tools for preliminary debris-flow assessment at regional scale, J. Mountain Sci. 14(12), 2017, doi:10.1007/s11629-017-4573-y.


### Tract phases and final stops (revised)

Each tract is labelled with a `phase`: 1 not activated, 2 flow, 3 stop, 4 stopped but flow resumes downstream, 5 after the final stop. On the main channel a stop is *final* when no valid flow (restart or re-activation by a tributary) occurs downstream on the main channel; on a lateral, when no valid restart occurs before the lateral joins the main channel. Spurious restarts (shorter than `min_restart_len`) do not count as flow.
