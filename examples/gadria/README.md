# Gadria test case

| File | Content |
|---|---|
| `gadria_dtm_2.5m.tif` | Pit-filled DTM of the Gadria catchment, 2.5 m, ETRS89 / UTM 32N (EPSG:32632), 1983 × 2011 cells (lossless compression) |
| `dfcc_config.json` | Saved DFCC configuration (threshold 50, kernel 50 m, basins 1–20 km², energy factor 0.4, whole-network on) |
| `reference/` | Original ArcGIS/TauDEM outputs (`RetClassDF.tif`, `DensitaDF.tif`, `Reticolo3D.shp`) used by `tests/test_gadria.py` |
| `expected/Runout_summary.csv` | Per-basin summary produced by DFCC 0.1.0 with `dfcc_config.json` |

Run it:

```bash
cd examples/gadria
dfcc run --config dfcc_config.json          # writes ./output (ignored by git)
```

or load `dfcc_config.json` from the GUI (*Load config*). Expected log highlights: 8,571 initiation points, natural break 27.08 points/ha,
402 network arcs (82.16 km), 2 basins (8.72 and 6.04 km²).

Validation against the reference outputs: `pytest tests/test_gadria.py`.
