# DFCC – method, implementation choices and validation

## 0. Optional pre-processing: DTM generalization
`--generalize CELL` aggregates the DTM to a coarser grid before everything else (NoData ignored; upper-left corner kept, the last partial row/column dropped). `average` is the exact area-weighted mean (each input cell weighted by its overlap with the output cell) and `median` the median of the input cells whose centre falls in the output cell: both are computed by DFCC (numba), without GDAL and without needing the CRS, so they are identical with every back-end. `bilinear` and `cubic` use GDAL (rasterio `reproject` or `osgeo.gdal.Warp`); with a GDAL build that returns an empty raster (seen with the GDAL of ArcGIS Pro) DFCC stops with a clear message and writes `DTM_generalized.tif`. Fill, flow directions and the whole chain then run on it. The channel threshold is multiplied by `(c0/c1)^(2n)` (A is counted in cells) unless `--generalize-keep-threshold` is given. Rationale and references: *Resolution* in the section *Scientific basis of the thresholds* below.

## 1. Hydrological chain (replica of the ModelBuilder + TauDEM workflow)
1. **PitRemove** (8-neighbour priority-flood; cells next to NoData or on the border drain out) — identical to TauDEM `pitremove` and to ArcGIS `Fill` (no z-limit).
2. **D∞** (`slp`) and **D8** (`p`, `sd8`) TauDEM, including flat resolution.
3. **AreaD8 -nc** (cells) → `ad8`; `sa = sd8^1 · ad8^0.5` (float32 as in the C++ code); **D8FlowPathExtremeUp -nc** (maximum upslope) → `ssa`; **Threshold** `ssa ≥ T` → `src` (network).
4. Raster algebra: `s38 = slp (slp<0.7812)`, `akm2 = ad8·res²/1e6`, `WB = 0.32·akm2^-0.2`; initiation `s38>WB & akm2<20`; slowing `0.0524<s38<0.1405` minus `inDF8`; stop `s38<0.0524` → classified network (1 propagation, 2 initiation, 3 slowing, 4 stop).
   All the constants above (and the exponents of step 3) are parameters with these defaults: `--s-max`, `--wb-k`, `--wb-exp`, `--max-init-area`, `--s-slow`, `--s-stop`, `--slope-exp`, `--area-exp` (`pipeline.Params`: `s_max`, `wb_k`, `wb_exp`, `area_max_km2`, `s_dep_max`, `s_stop`, `slope_exp`, `area_exp`). They are passed to the numba kernel as float32, exactly like the original constants, so the defaults stay bit-identical to ArcGIS.
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

Stefano Crema, Marco Cavalli, Alessandro Sarretta — CNR GEO, 2026. Method: Cavalli, M., Crema, S., Trevisani, S., Marchi, L. (2017). GIS tools for preliminary debris-flow assessment at regional scale. J. Mountain Sci. 14(12), 2498-2510, doi:10.1007/s11629-017-4573-y.


### Tract phases and final stops (revised)

Each tract is labelled with a `phase`: 1 not activated, 2 flow, 3 stop, 4 stopped but flow resumes downstream, 5 after the final stop. On the main channel a stop is *final* when no valid flow (restart or re-activation by a tributary) occurs downstream on the main channel; on a lateral, when no valid restart occurs before the lateral joins the main channel. Spurious restarts (shorter than `min_restart_len`) do not count as flow.

## Scientific basis of the thresholds

DFCC reproduces the empirical, purely morphometric procedure of Cavalli et al. (2017); the thresholds are not tuned by the software but inherited from the literature below (section 1.1 of the paper). They can be re-parametrised for other settings, but the defaults replicate the original ArcGIS workflow bit by bit.

**Channel network - slope-area threshold.** Channels are the cells exceeding a threshold of the Stream Power Index `SPI = A^0.5 · S` (Marchi & Dalla Fontana 2005), computed on D8 flow directions (O'Callaghan & Mark 1984). As in the original TauDEM workflow (`AreaD8 -nc`, `SlopeArea`, `D8FlowPathExtremeUp`), **A is the D8 contributing area counted in cells** and S the D8 slope (m/m), so the threshold value depends on the cell size (see [Advanced parameters](#advanced-parameters-and-dtm-generalization)). Slope-area channel-initiation thresholds follow Montgomery & Dietrich (1992), Montgomery & Foufoula-Georgiou (1993) and Desmet et al. (1999). The threshold value (`-t`, default 50) must be calibrated on field observations and on the drainage density of the area. Local slope is the drop to the steepest-descent neighbour (Vianello et al. 2009).

**Debris-flow initiation - area-slope threshold.** A network cell is a potential initiation point when its slope exceeds

```
S = 0.32 · A^-0.2        (A = contributing area in km², S = local D∞ slope in m/m)
```

the empirical envelope derived by Zimmermann et al. (1997) from debris-flow events in Switzerland, in the spirit of the models of Wichmann & Becht (2005) and Horton et al. (2013).
The same curve is Eq. 1 of Horton et al. (2013) — `tan β = 0.32 · S_uca^-0.2`, S_uca in km², the lower limit for "rare" events in the central Alps,
after Rickenmann & Zimmermann (1993) and Heinimann (1998) — which Horton et al. apply for S_uca < 2.5 km² and recommend using with a ~10 m DEM.
The classification slope is the D∞ slope (Tarboton 1997). Kaless (2006) verified it against initiation areas in the Autonomous Province of Trento (eastern Italian Alps). Two filters complete the rule: an upper local slope of **38°** (about the internal friction angle of alpine debris), which removes very steep bedrock-like cells where sediment is scarce, and an upper drainage-area limit above which channels are dominated by bedload and suspended transport (**10 km²** in the paper, after Marchi & D'Agostino 2004; the original ArcGIS model, and therefore DFCC's default, uses **20 km²**).

**Propagation, slowing and stop - slope classes.** Debris flows start depositing on slopes of roughly 6°-10° and usually stop at about 3°-5° (Benda 1985; Vandre 1985; Burton & Bathurst 1998). Following a cautionary approach, the remaining network cells are classified as

| Local slope | Class |
|---|---|
| > 8° (tan = 0.1405) and not initiation | 1 - Propagation |
| 3° - 8° | 3 - Slowing (deceleration) |
| < 3° (tan = 0.0524) | 4 - Stop |

**Runout - energy rule.** The runout distance follows the empirical relation of Vandre (1985), `W = α · Δh` with `α = 0.4`, and the rule-based transport model of Burton & Bathurst (1998). Differently from the original thresholds (flow continues above 10°, stops between 4° and 10° or at 4°), DFCC uses the 8° and 3° limits above: the flow halts when `distance on slopes < 8°  >  0.4 · elevation lost on slopes > 8°`, and may restart at a downstream initiation cell.

**Initiation density.** Initiation points are turned into a kernel-density map (50 m radius, points/ha) and split in two classes with natural breaks, to rank the most hazardous reaches (Cavalli et al. 2017).

**Resolution.** These thresholds were developed with DTMs of about 10 m (Horton et al. 2013; Zhang & Montgomery 1994; Quinn et al. 1995) and describe
reach-scale channel slopes. Slopes computed on very fine LiDAR DTMs are systematically different — steeper on local steps, flatter on the
treads between them (Vianello et al. 2009; Kienzle 2004) — which shifts cells across the 8° / 3° boundaries and across the non-linear
initiation curve. Generalize fine DTMs (5–10 m) or re-calibrate the thresholds.

### References

* Benda, L.E. (1985). Behaviour and effect of debris flows on streams in the Oregon Coast Range. In: *Delineation of landslide, flash flood and debris flow hazards in Utah*, Utah Water Research Laboratory, Logan, 153-162.
* Burton, A., Bathurst, J.C. (1998). Physically based modelling of shallow landslide sediment yield at a catchment scale. *Environmental Geology* 35(2-3), 89-99. <https://doi.org/10.1007/s002540050296>
* Cavalli, M., Crema, S., Trevisani, S., Marchi, L. (2017). GIS tools for preliminary debris-flow assessment at regional scale. *Journal of Mountain Science* 14(12), 2498-2510. <https://doi.org/10.1007/s11629-017-4573-y>
* Desmet, P.J.J., Poesen, J., Govers, G., Vandaele, K. (1999). Importance of slope gradient and contributing area for optimal prediction of the initiation and trajectory of ephemeral gullies. *Catena* 37(3-4), 377-392. <https://doi.org/10.1016/S0341-8162(99)00027-2>
* Heinimann, H.R. (1998). *Methoden zur Analyse und Bewertung von Naturgefahren.* Umwelt-Materialien 85, BUWAL, Bern (in German); cited after Horton et al. (2013).
* Horton, P., Jaboyedoff, M., Rudaz, B., Zimmermann, M. (2013). Flow-R, a model for susceptibility mapping of debris flows and other gravitational hazards at a regional scale. *Natural Hazards and Earth System Sciences* 13(4), 869-885. <https://doi.org/10.5194/nhess-13-869-2013>
* Kaless, G. (2006). *Il torrente Sarca di Val Genova. Studio geomorfologico per la prevenzione e la mitigazione del rischio geo-idrologico.* Master thesis, University of Padova (in Italian).
* Kienzle, S. (2004). The effect of DEM raster resolution on first order, second order and compound terrain derivatives. *Transactions in GIS* 8(1), 83-111. <https://doi.org/10.1111/j.1467-9671.2004.00169.x>
* Marchi, L., D'Agostino, V. (2004). Estimation of debris-flow magnitude in the Eastern Italian Alps. *Earth Surface Processes and Landforms* 29(2), 207-220. <https://doi.org/10.1002/esp.1027>
* Marchi, L., Dalla Fontana, G. (2005). GIS morphometric indicators for the analysis of sediment dynamics in mountain basins. *Environmental Geology* 48(2), 218-228. <https://doi.org/10.1007/s00254-005-1292-4>
* Montgomery, D.R., Dietrich, W.E. (1992). Channel initiation and the problem of landscape scale. *Science* 255(5046), 826-830. <https://doi.org/10.1126/science.255.5046.826>
* Montgomery, D.R., Foufoula-Georgiou, E. (1993). Channel network source representation using digital elevation models. *Water Resources Research* 29(12), 3925-3934. <https://doi.org/10.1029/93WR02463>
* O'Callaghan, J.F., Mark, D.M. (1984). The extraction of drainage networks from digital elevation data. *Computer Vision, Graphics, and Image Processing* 28(3), 323-344. <https://doi.org/10.1016/S0734-189X(84)80011-0>
* Quinn, P.F., Beven, K.J., Lamb, R. (1995). The ln(a/tan β) index: how to calculate it and how to use it within the TOPMODEL framework. *Hydrological Processes* 9(2), 161-182. <https://doi.org/10.1002/hyp.3360090204>
* Rickenmann, D., Zimmermann, M. (1993). The 1987 debris flows in Switzerland: documentation and analysis. *Geomorphology* 8(2-3), 175-189. <https://doi.org/10.1016/0169-555X(93)90036-2>
* Tarboton, D.G. (1997). A new method for the determination of flow directions and upslope areas in grid digital elevation models. *Water Resources Research* 33(2), 309-319. <https://doi.org/10.1029/96WR03137>
* Vandre, B.C. (1985). Rudd Creek debris flow. In: *Delineation of landslide, flash flood and debris flow hazards in Utah*, Utah Water Research Laboratory, Logan, 117-131.
* Vianello, A., Cavalli, M., Tarolli, P. (2009). LiDAR-derived slopes for headwater channel network analysis. *Catena* 76(2), 97-106. <https://doi.org/10.1016/j.catena.2008.09.012>
* Wichmann, V., Becht, M. (2005). Modelling of geomorphic processes in an alpine catchment. In: Atkinson, P.M., et al. (eds), *GeoDynamics*, 151-167.
* Zhang, W., Montgomery, D.R. (1994). Digital elevation model grid size, landscape representation, and hydrologic simulations. *Water Resources Research* 30(4), 1019-1028. <https://doi.org/10.1029/93WR03553>
* Zimmermann, M., Mani, P., Gamma, P., et al. (1997). *Murganggefahr und Klimaaenderung - ein GIS-basierter Ansatz.* Schlussbericht NFP 31, Zurich (in German).

