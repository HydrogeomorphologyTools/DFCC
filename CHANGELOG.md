# Changelog

## 0.4.0 — testing release (2026-10-15)

**Advanced parameters and DTM generalization.** The defaults are unchanged and still reproduce the original ArcGIS/TauDEM workflow bit by bit
(Gadria test suite).

* **DTM resolution note** (README, Help, GUI, QGIS/ArcGIS help): the default thresholds come from literature based on ~10 m, non-LiDAR DTMs
  and describe reach-scale slopes; very fine DTMs alter slopes and classes. A warning is logged, and shown in the GUI, below 5 m cell size.
* **DTM generalization** (optional pre-processing): `--generalize CELL` with `--generalize-method average|median|bilinear|cubic`; the generalized
  DTM (`DTM_generalized.tif`) then goes through fill, flow directions and the whole procedure. The channel threshold is rescaled by
  `(old/new cell)^(2n)` because the contributing area is counted in cells (`--generalize-keep-threshold` to disable).
* **Custom thresholds**: channel-extraction exponents (`--slope-exp`, `--area-exp`), initiation curve (`--wb-k`, `--wb-exp`, `--max-init-area`)
  and slope classes (`--s-slow`, `--s-stop`, `--s-max`). Inconsistent values are refused; non-default values are logged and saved in the JSON
  configuration.
* **GUI**: new *Advanced* tab beside *Parameters* (warning box, generalization, thresholds with the equivalent angle, *Reset to defaults*,
  ● marker and "not the standard Procedura DF" notice when values differ from the defaults).
* **QGIS plugin / ArcGIS Pro toolbox**: the same settings as *Advanced parameters* (collapsed by default). The executable fallback passes only
  non-default values, so older executables keep working with default settings.
* **Packaging**: `packaging/build_exe.bat [folder|onefile|all]`; new `dfcc_onefile.spec` builds a single self-contained `DFCC.exe`.
* **Documentation fixes**: the contributing area of the channel threshold is in *cells* (TauDEM `AreaD8 -nc`), not m²; the area of the
  initiation curve is in *km²* (as in Horton et al. 2013, Eq. 1), not m²; complete author lists and issue numbers in the references, verified
  against Crossref; new references (Horton et al. 2013 Eq. 1 source, Rickenmann & Zimmermann 1993, Heinimann 1998, Tarboton 1997,
  Zhang & Montgomery 1994, Quinn et al. 1995, Kienzle 2004); install instructions point to the GitHub package (`dfcc` is not on PyPI).
* **Fixes**: ArcGIS toolbox value-list filter applied to the wrong parameter; QGIS metadata repository/homepage URL;
  `DFCC.exe` now always uses its own bundled PROJ/GDAL data (when launched from QGIS or ArcGIS Pro it inherited their
  `PROJ_LIB`/`GDAL_DATA` and CRS parsing failed), and the plug-ins start it with those variables removed; no crash when no
  initiation cell exists (empty high-density layer instead of a natural-breaks error).
* `average` and `median` generalization are computed by DFCC (numba) and are identical with every GDAL back-end; tested
  with rasterio, the GDAL of QGIS 3.34 and the GDAL of ArcGIS Pro.

## 0.3.2 — testing release (2026-10-15)

First public release of **DFCC — Debris-Flow Channel Classification**.

* Stand-alone Python/numba implementation of Procedura DF (pit removal, D8, D∞, contributing area, slope-area, classification, kernel density, natural breaks), verified bit-by-bit against ArcGIS/TauDEM on the Gadria test case.
* Main-channel runout (energy rule, restarts, spurious restarts, final stop), basin selection by area / confluences / pour points, extension of the profile below the outlet (distance or polygon).
* Optional whole-network runout with worst-case merge at confluences; final stops on laterals marked separately.
* Initiation points for MSF (hot-spot detection with alignment pruning).
* GUI (dark theme, layer check-boxes, profiles, profile matrix, summary table, console, JSON configuration, illustrated Help), CLI, QGIS Processing plugin, ArcGIS Pro toolbox, pip package, Windows executable (PyInstaller).
