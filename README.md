<p align="center"><img src="docs/logo.png" width="110" alt="DFCC logo"></p>

<h1 align="center">DFCC — Debris-Flow Channel Classification</h1>

<p align="center">
<b>Where can a debris flow start, how far can it travel, and where does it stop?</b><br>
A free, stand-alone implementation of the <i>Procedura DF</i> — GUI · command line · QGIS plugin · ArcGIS Pro toolbox · pip package · Windows executable.
</p>

<p align="center">
<a href="LICENSE"><img alt="License: GPL v2+" src="https://img.shields.io/badge/license-GPL--2.0--or--later-blue"></a>
<img alt="Status: testing" src="https://img.shields.io/badge/status-testing-orange">
<img alt="Version" src="https://img.shields.io/badge/version-0.3.2-informational">
<img alt="Python" src="https://img.shields.io/badge/python-3.9%2B-3776ab">
<img alt="No ArcGIS needed" src="https://img.shields.io/badge/ArcGIS%20%2F%20TauDEM-not%20required-success">
</p>

<p align="center"><img src="docs/images/gui_map.png" alt="DFCC graphical interface" width="900"></p>

> **Status — v0.3.2 (testing).** The numerical core is verified against the original ArcGIS/TauDEM workflow (see [Validation](#validation));
> the GUI, the plugins and the runout extensions are young. Bug reports and test cases are very welcome (see [Contact](#authors-and-contact)).

## Contents

1. [What DFCC does](#what-dfcc-does)
2. [Installation](#installation)
3. [Quick start](#quick-start)
4. [How it works](#how-it-works)
5. [Example results — Gadria test case](#example-results--gadria-test-case)
6. [Outputs](#outputs)
7. [Parameters](#parameters)
8. [Validation](#validation)
9. [The graphical interface and the built-in Help](#the-graphical-interface-and-the-built-in-help)
10. [Repository layout](#repository-layout) · [The `old/` folder](#the-old-folder)
11. [Citation](#citation) · [Authors and contact](#authors-and-contact) · [License](#license)

## What DFCC does

Starting from a **DTM** only, DFCC answers four questions about every debris-flow-prone catchment:

| Step | Question | Result |
|---|---|---|
| 1 · Channel classification | Which parts of the channel network are prone to **initiation**, **propagation**, **slowing** or **stopping** of a debris flow? | `ClassifiedNetwork.tif`, `Network_classes.shp`, `Network3D.shp` |
| 2 · Initiation density | Where do potential initiation points **cluster**? | `InitiationDensity.tif` (points/ha), `HighDensity.shp` (natural breaks) |
| 3 · Runout | Along the main channel of each basin, where does the flow **start, stop, restart** and **stop for good**? | `Runout_mainchannel.shp`, `Runout_events.shp`, `Runout_summary.csv` |
| 4 · MSF input | Which points should seed a debris-flow **runout simulation** (MSF / Flow-R style)? | `InitiationPoints_MSF.shp` |

An optional **whole-network runout** applies the same energy rule to *every* channel of the selected basins (not only the main one), propagating
the locally worst condition at confluences — useful to see which tributaries are able to deliver debris to the main channel.

No ArcGIS, no TauDEM, no MPI: every routine (Fill, D8, D∞, D8 contributing area, slope-area, kernel density, stream-to-feature, interpolate-shape) is
re-implemented in Python/numba and **verified bit-by-bit against the originals**. A 2011 × 1983-cell DTM runs from DTM to vector network and density in about 5 s.

## Installation

**Windows executable (no Python needed)** — download `DFCC-windows.zip` from the [Releases](../../releases) page, unzip and run `DFCC.exe`
(no arguments → graphical interface; with arguments → command line, e.g. `DFCC.exe run dtm.tif -o out --runout`).

**pip** (Python ≥ 3.9):

```bash
pip install "dfcc[gui] @ git+https://github.com/HydrogeomorphologyTools/DFCC"      # GUI + CLI
pip install "dfcc @ git+https://github.com/HydrogeomorphologyTools/DFCC"           # CLI only
```

or from a clone: `pip install -e ".[gui,test]"`.

**QGIS** (≥ 3.22) — copy the folder [`qgis_plugin/dfcc_qgis`](qgis_plugin/dfcc_qgis) into your QGIS plugins directory and enable *DFCC* in the Plugin Manager.
The algorithm appears in the Processing Toolbox. It uses the `dfcc` Python package when available in the QGIS Python, otherwise the stand-alone
executable (set the environment variable `DFCC_EXE` to the path of `DFCC.exe`). Results are loaded with ready-made styles.

**ArcGIS Pro** — add [`arcgis_toolbox/DFCC.pyt`](arcgis_toolbox/DFCC.pyt) to a project (*Catalog → Toolboxes → Add Toolbox*). Same logic: the `dfcc` package if
importable, otherwise `DFCC_EXE`.

## Quick start

```bash
dfcc gui                                       # graphical interface

cd examples/gadria                             # run the bundled test case from a saved configuration
dfcc run --config dfcc_config.json

dfcc run dtm.tif -o out --runout               # your own DTM: procedure + main channels + runout + MSF points
dfcc run dtm.tif -o out --runout --whole-network --extend-downstream 500
dfcc run dtm.tif -o out --runout --pour-points outlets.shp --extend-polygon catchment_and_fan.shp
dfcc fill dtm.tif dtm_fill.tif                 # depression filling only (identical to ArcGIS Fill)
```

The DTM must be in a **projected CRS with square cells**. A pit-filled DTM can be used directly; otherwise tick *Fill depressions* (`--prefill`).
The complete parameter set can be saved and reloaded as JSON from the GUI and from the CLI (`--save-config`, `--config`).

## How it works

<p align="center"><img src="src/dfcc/gui/help/workflow.png" alt="Workflow" width="700"></p>

1. **Terrain analysis** (TauDEM-equivalent): pit removal, D8 flow directions, D∞ slope, D8 contributing area **A**, slope-area index `S·A^0.5`, and the channel network from a slope-area threshold.
2. **Channel classes** — every network cell receives one of four classes from its local slope **s** and contributing area **A** (km²):

   | Class | Meaning | Rule |
   |---|---|---|
   | 2 | **Initiation** | `s > WB`, with `WB = 0.32·A^-0.2` and `A < 20 km²` |
   | 1 | **Propagation** | `s ≥ 0.1405` and not an initiation cell |
   | 3 | **Slowing** | `0.0524 < s < 0.1405` |
   | 4 | **Stop zone** | `s < 0.0524` |

3. **Initiation density** — the initiation cells are turned into points and a quartic **kernel density** (radius 50 m, points/ha) is computed; a 2-class **natural-breaks** (Fisher–Jenks) split of the non-zero density defines the high-density areas.
4. **Runout energy rule** — walking downstream along the main channel:
   `L` = cumulated elevation drop on class 1–2 cells; `K` = cumulated distance on class 3–4 cells.
   The flow **stops** at the first cell where `K > 0.4·L`, **restarts** at the next initiation cell (L and K reset), and a restart that dies within 30 m is *spurious*.
   The **final stop** is the last stop with no valid restart downstream.

   <p align="center"><img src="src/dfcc/gui/help/runout_rule.png" alt="Runout rule" width="620"></p>

5. **Whole-network mode (optional)** — the same rule on every channel cell, processed upstream → downstream. Where flowing branches merge, the one with the **largest energy margin** `0.4·L − K` is propagated (an envelope — states are never summed). A flowing tributary can re-activate a stopped trunk. The main-channel results do not change.

More detail in [`docs/METHOD.md`](docs/METHOD.md) and in the built-in Help.

## Example results — Gadria test case

The folder [`examples/gadria`](examples/gadria) contains the 2.5 m DTM of the Gadria catchment (Eastern Alps, UTM 32N), the saved configuration, and the original
ArcGIS/TauDEM outputs used for the validation. All figures below are produced by [`docs/make_figures.py`](docs/make_figures.py) with
`examples/gadria/dfcc_config.json` (threshold 50, kernel radius 50 m, basins 1–20 km², energy factor 0.4, whole-network on).

### 1 · Classified channel network

<p align="center"><img src="docs/images/01_classified_network.png" width="760" alt="Classified channel network"></p>

The 402 channel arcs (82.2 km) are split into **initiation** (red, 7,975 cells), **propagation** (blue, 17,196), **slowing** (orange, 1,772) and **stop** (green, 974 cells).
Initiation cells sit on the steep upper tributaries of both basins; the stop and slowing classes concentrate where the main trunks flatten out
towards the valley floor. This layer is the input of everything that follows and is identical, pixel for pixel, to the ArcGIS/TauDEM result.

### 2 · Initiation density and high-density areas

<p align="center"><img src="docs/images/02_initiation_density.png" width="760" alt="Initiation density"></p>

8,571 potential initiation points produce a kernel-density surface with a maximum of 153 points/ha. The natural break between "low" and "high" density falls at
27.1 points/ha and delimits 107 high-density polygons (red outlines): the sectors of the slopes where debris flows are most likely to start. They are
spread over the headwater gullies of both basins.

### 3 · Main channel runout

<p align="center"><img src="docs/images/03_main_channel_runout.png" width="760" alt="Main channel runout"></p>

The two basins found automatically (**Basin 1**, 8.72 km²; **Basin 2**, 6.04 km²) are followed along their main channel (largest contributing area at each confluence).
Colours show the *phase* of the flow along the channel: <span style="color:#ffd60a">yellow</span> not yet activated, <span style="color:#1f6feb">blue</span> flowing,
<span style="color:#f77f00">orange</span> stop, <span style="color:#6ec6ff">light blue</span> stopped but the flow resumes downstream, <span style="color:#2a9d3c">green</span> after the final stop.
Basin 1 (7,064 m long) alternates many short stops with restarts on its lower reach (90 stops, 15 valid restarts, 75 spurious ones) but the flow **reaches the outlet**.
Basin 2 (3,724 m) has a **final stop** at 3,035 m from the head (z = 1,489 m), 689 m before the outlet: in this model, debris flows of that channel do not reach the confluence.

### 4 · Longitudinal profile with events

<p align="center"><img src="docs/images/04_profile_basin1.png" width="760" alt="Profile of basin 1"><br>
<img src="docs/images/04_profile_basin2.png" width="760" alt="Profile of basin 2"></p>

The profile of each main channel is coloured by class and carries the runout events (initiation ▲, intermediate stop ■, restart ▼, final stop ✖). The dashed line in
the first plot is the same profile against the **3-D distance** (7,293 m instead of 7,064 m for Basin 1). In Basin 2 the distance travelled on slowing and stop cells
exceeds `0.4·L` at 3,035 m from the head, which produces the final stop (green ✖).

### 5 · Whole-network runout

<p align="center"><img src="docs/images/05_whole_network_runout.png" width="760" alt="Whole network runout"></p>

With the optional whole-network mode every tributary is evaluated. In Basin 1, 9,781 of the 13,528 channel cells (24.5 km) are in flow and the network
outlet is reached by the flow; in Basin 2, 12,532 of 14,292 cells (31.3 km) flow but the outlet is in a stopped state (margin −1.7 m).
<span style="color:#8e44ad">◆ Purple diamonds</span> are **final stops on laterals** (Basin 1: 10; Basin 2: 3) — expected and harmless for the main channel;
a <span style="color:#c2185b">✚ magenta plus</span> would flag a final stop on the main channel caused by the energy of a lateral (none in this example). Thin yellow
tracts are channels upstream of any initiation cell. The thick main-channel layer is drawn underneath so that both results can be compared.

### 6 · Initiation points for MSF

<p align="center"><img src="docs/images/06_msf_initiation_points.png" width="760" alt="MSF initiation points"></p>

One candidate point is placed at the head of each high-density area, snapped to the network (50 m) and pruned when it lies downstream of a higher aligned
candidate: 131 candidates, **73 kept** (yellow) and 58 dropped (grey). The kept points are written to `InitiationPoints_MSF.shp` and can seed an MSF/Flow-R runout simulation directly.

### 7 · Profile matrix

<p align="center"><img src="docs/images/07_profile_matrix.png" width="760" alt="Profile matrix"></p>

All basins side by side (titles give basin number, area, 2-D and 3-D length): handy to compare the energy balance of many catchments at a glance.

## Outputs

| File | Content |
|---|---|
| `ClassifiedNetwork.tif` | 1 propagation · 2 initiation · 3 slowing · 4 stop |
| `InitiationDensity.tif` | Kernel density of initiation points (points/ha) |
| `HighDensity.tif` / `.shp` | High-density areas (2-class natural breaks of the non-zero density) |
| `Network3D.shp`, `Network_classes.shp` | Network with elevation; network split by class (ready to style) |
| `Runout_mainchannel.shp` | Main channel tracts with `class`, `df_yn` and **`phase`** (1 not activated · 2 flow · 3 stop · 4 stopped but flow resumes · 5 after final stop) |
| `Runout_events.shp` | Initiation, intermediate stops, restarts, spurious restarts, **final stop** |
| `Runout_points.shp` | Point profile (`DF_YN`, `L_drop`, `K_dist`, cumulated distance) |
| `Runout_summary.csv` | One row per basin: area, 2-D/3-D length, stops, restarts, final-stop position and distance to the outlet, `net_*` columns in whole-network mode |
| `Runout_network.shp`, `Runout_network_events.shp` | *(whole-network mode)* all channels with `phase`, `main` flag, L, K, margin; events with lateral final stops |
| `InitiationPoints_MSF.shp`, `…_candidates.shp` | Seed points for MSF runout simulations, before and after pruning |

## Parameters

| Option (CLI) | Default | Meaning |
|---|---|---|
| `-t, --threshold` | 50 | Slope-area threshold defining the channel network |
| `--prefill` | off | Fill depressions before the analysis (ArcGIS-identical) |
| `--kd-radius` | 50 m | Kernel-density radius |
| `--min-area / --max-area / --split-area` | 1 / 20 / 2 km² | Basin selection: outlets between min and max area, split at confluences whose two branches both exceed *split* |
| `--pour-points` | – | Shapefile of pour points (overrides the automatic selection) |
| `--main-branch` | `area` | Main channel: `area` (largest contributing area at each confluence), `longest` or `highest` |
| `--energy-factor` | 0.4 | The flow stops when `K > factor · L` |
| `--min-restart-len` | 30 m | Restarts dying within this length are *spurious* |
| `--extend-downstream`, `--extend-polygon` | off | Continue the profile below the outlet (e.g. over a fan), for a distance or until a polygon is left |
| `--whole-network` | off | Apply the energy rule to every channel of the selected basins |
| `--no-hotspots`, `--hotspot-snap`, `--no-prune` | – | MSF initiation points options |

`dfcc run --help` lists everything.

## Validation

On the Gadria 2.5 m test (`examples/gadria`, reference ArcGIS/TauDEM outputs in `examples/gadria/reference`; run `pytest tests`):

| Output | Result |
|---|---|
| Classified network (classes 1–4) | 0 different pixels out of 27,917 |
| Initiation density (kernel density) | bit-identical (0 different cells) |
| 3-D network shapefile | 402/402 arcs, same vertices (Δxy = 0, Δz ≈ 1e‑9) |
| Fill | identical to ArcGIS Fill (ArcMap 10.8) on a synthetic DEM with pits, flats and NoData |
| Runout stops | same 4 stop points as the Procedura-DF Excel example |

The only intentional difference is the natural-breaks threshold: ArcGIS approximates Jenks breaks on a sample of the data, DFCC computes the exact optimum
(on Gadria the threshold is 27.08 vs 28.26 points/ha in ArcGIS), which only changes the outline of a few small high-density patches.

## The graphical interface and the built-in Help

<table>
<tr>
<td width="50%"><img src="docs/images/gui_profile.png" alt="Profile tab"><br><sub><b>Profile</b> — one basin, optional 3-D distance overlay.</sub></td>
<td width="50%"><img src="docs/images/gui_matrix.png" alt="Profile matrix tab"><br><sub><b>Profile matrix</b> — all basins in a grid.</sub></td>
</tr>
<tr>
<td><img src="docs/images/gui_summary.png" alt="Basin summary tab"><br><sub><b>Basin summary</b> — the content of <code>Runout_summary.csv</code>.</sub></td>
<td><img src="docs/images/gui_help.png" alt="Help window"><br><sub><b>Help</b> (button <i>? Help</i> or F1) — illustrated guide to data, parameters, colours, outputs and troubleshooting.</sub></td>
</tr>
</table>

Layer check-boxes on the map, basin labels, a detailed time-stamped **Console** (save/clear), JSON save/load of the whole configuration, and a dark theme.
Map legends are kept outside the map.

## Repository layout

```
DFCC/
├── src/dfcc/          Python package (core algorithms, pipeline, CLI, GUI, help)
├── examples/gadria/   test DTM, saved configuration, reference ArcGIS/TauDEM outputs
├── tests/             pytest suite (bit-level comparison with the originals)
├── docs/              METHOD.md, logo, figure/screenshot scripts and images
├── qgis_plugin/       QGIS Processing plugin
├── arcgis_toolbox/    ArcGIS Pro Python toolbox (.pyt)
├── packaging/         PyInstaller spec and build scripts for the stand-alone executable
├── old/               snapshot of the previous Procedura-DF repository (ArcGIS/TauDEM version)
└── .github/workflows/ CI tests and executable build
```

Build the Windows executable locally with `packaging\build_exe.bat` (or let the *release* workflow do it when a version tag is pushed).

### The `old/` folder

[`old/`](old) is an unmodified copy of the previous **Procedura-DF** repository (the ArcGIS/TauDEM implementation), kept for reference and as a backup.
The original repository remains available in the same GitHub account.

## Citation

If you use DFCC, please cite the method paper and this software:

* *GIS tools for preliminary debris-flow assessment at regional scale.* Journal of Mountain Science, 14(12), 2017. <https://doi.org/10.1007/s11629-017-4573-y>
* Crema S., Cavalli M., Sarretta A. (2026). *DFCC — Debris-Flow Channel Classification*, version 0.3.2. <https://github.com/HydrogeomorphologyTools/DFCC> (see [`CITATION.cff`](CITATION.cff)).

The D8/D∞ routines derive from the native rewrites of *SedInConnect 3.2* ([HydrogeomorphologyTools](https://github.com/HydrogeomorphologyTools)), themselves ports of TauDEM (D. Tarboton).

## Authors and contact

**Stefano Crema** (main contact) · **Marco Cavalli** · **Alessandro Sarretta** — CNR GEO (Istituto di Geoscienze), 2026

* Contact: Stefano Crema — <stefano.crema@cnr.it>
* Bugs and feature requests: [GitHub Issues](../../issues)
* Other authors: marco.cavalli@cnr.it · alessandro.sarretta@cnr.it

## License

DFCC is free software released under the **GNU General Public License v2 or later** — see [LICENSE](LICENSE).
