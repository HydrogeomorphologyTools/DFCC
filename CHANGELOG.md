# Changelog

## 0.3.2 — testing release (2026-10-15)

First public release of **DFCC — Debris-Flow Channel Classification**.

* Stand-alone Python/numba implementation of Procedura DF (pit removal, D8, D∞, contributing area, slope-area, classification, kernel density, natural breaks), verified bit-by-bit against ArcGIS/TauDEM on the Gadria test case.
* Main-channel runout (energy rule, restarts, spurious restarts, final stop), basin selection by area / confluences / pour points, extension of the profile below the outlet (distance or polygon).
* Optional whole-network runout with worst-case merge at confluences; final stops on laterals marked separately.
* Initiation points for MSF (hot-spot detection with alignment pruning).
* GUI (dark theme, layer check-boxes, profiles, profile matrix, summary table, console, JSON configuration, illustrated Help), CLI, QGIS Processing plugin, ArcGIS Pro toolbox, pip package, Windows executable (PyInstaller).
