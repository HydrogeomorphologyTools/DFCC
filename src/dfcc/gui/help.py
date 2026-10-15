"""Help window of the DFCC GUI: navigable, illustrated documentation (HTML in a QTextBrowser)."""
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QTextBrowser, QSplitter, QVBoxLayout, QPushButton
from .. import __version__

HELP_DIR = Path(__file__).parent / "help"

CSS = """
body { background:#0e1a24; color:#e8f1f7; font-family:'Segoe UI',Inter,Arial,sans-serif; font-size:10.5pt; line-height:1.45; }
h1 { color:#7fd1f2; font-size:20pt; margin-bottom:2px; } h2 { color:#7fd1f2; font-size:14.5pt; border-bottom:1px solid #26405a; padding-bottom:3px; margin-top:22px; }
h3 { color:#f4a261; font-size:11.5pt; margin-bottom:2px; } a { color:#7fd1f2; }
table { border-collapse:collapse; margin:6px 0; } td, th { border:1px solid #26405a; padding:4px 8px; vertical-align:top; } th { background:#16293a; color:#7fd1f2; text-align:left; }
code { background:#16293a; color:#ffd166; padding:0 3px; } .note { background:#16293a; border-left:4px solid #7fd1f2; padding:6px 10px; }
.warn { background:#2a1d14; border-left:4px solid #f4723c; padding:6px 10px; } .sub { color:#8aa4b8; }
"""

SECTIONS = [
    ("overview", "Overview"), ("workflow", "Workflow"), ("start", "Quick start"), ("data", "1 · Data"), ("proc", "2 · DF procedure"),
    ("advanced", "Advanced · resolution"), ("classes", "Channel classes"), ("density", "Initiation density"), ("part2", "3 · Main channels & runout"),
    ("rule", "Runout energy rule"), ("msf", "MSF initiation points"), ("outputs", "Output files"), ("cli", "Command line & config"),
    ("plugins", "QGIS · ArcGIS · pip · exe"), ("tips", "Tips & troubleshooting"), ("about", "About / licence"),
]


def html() -> str:
    h = HELP_DIR
    def img(n, w=None):          # images are pre-sized to their display width
        return f'<p align="center" style="line-height:100%"><img src="{n}"></p>'
    return f"""<html><head><style>{CSS}</style></head><body>
<a name="overview"></a>
<table width="100%"><tr><td style="border:none" width="90"><img src="logo.png" width="80"></td>
<td style="border:none"><h1>DFCC {__version__}</h1><span class="sub">Debris-Flow Channel Classification · stand-alone, free and open source</span></td></tr></table>
<p>DFCC classifies every cell of the channel network according to its <b>propensity for debris-flow initiation, propagation, slowing and stopping</b>,
maps where potential initiation points cluster (<b>kernel density</b> + <b>natural breaks</b>) and, optionally, follows the <b>main channel of each basin</b>
with the morphometric <b>runout (energy) rule</b> to locate stops, restarts and the final stop. It replicates the <i>Procedura DF</i> ArcGIS/TauDEM model
(Cavalli, Crema, Viero, Marchi) without needing either: classes, density and network geometry are verified identical to the originals.</p>

<a name="workflow"></a><h2>Workflow</h2>{img("workflow.png", 700)}
<p><b>Part 1</b> runs the full Procedura DF on a DTM. <b>Part 2</b> is optional and works on the result: it selects basins, traces the main channel, applies the runout rule
and proposes initiation points snapped on the network for models such as MSF.</p>

<a name="start"></a><h2>Quick start</h2>
<ol><li>In <b>1 · Data</b> choose the <b>DTM</b> (GeoTIFF, projected CRS, square cells) and an <b>Output</b> folder.</li>
<li>Leave the defaults in <b>2 · DF procedure</b> (they reproduce the original procedure) and tick <b>3 · Main channels and runout</b> if you want part 2.</li>
<li>Press <b>▶ Run DFCC</b>. The first run compiles the numerical kernels (about a minute); later runs start immediately.</li>
<li>Use the layer check-boxes above the map, the <b>Profile</b> tab (choose the basin; tick <i>Overlay 3-D distance</i> to add the dashed 3-D/slope-distance profile in the same plot), the optional <b>Profile matrix</b> (all basins side by side; titles give basin number, area and length) and the <b>Basin summary</b> tab. On the map each main channel carries a <b>Basin n</b> label with its area. Everything is also written to the output folder.</li>
<li><b>Save config…</b> stores all parameters in a JSON file; <b>Load config…</b> restores them (the same file works with the command line).</li></ol>
{img("gui.png", 700)}

<a name="data"></a><h2>1 · Data</h2>
<table><tr><th>Item</th><th>Meaning</th></tr>
<tr><td>DTM</td><td>Elevation raster (GeoTIFF/ASC/IMG). Projected CRS in metres; square cells. NoData cells are respected (the DTM can be clipped to a catchment).</td></tr>
<tr><td>Output</td><td>Folder for all results (created if missing).</td></tr>
<tr><td>Prefix</td><td>Optional text added to every output file name.</td></tr></table>
<div class="note">Tip: do not clip the DTM with a 1-cell-wide neck just above a fan or a confluence; the flow stops at such a neck. Use the full DTM and a pour point / <i>Extend past outlet</i> instead.</div>
<div class="warn"><b>DTM resolution.</b> The default thresholds come from literature based on DTMs of about <b>10 m</b> (not LiDAR) and describe
<b>reach-scale</b> slopes. With a very fine DTM (below 5 m DFCC shows a warning) read <a href="#advanced">Advanced · resolution</a>.</div>

<a name="proc"></a><h2>2 · DF procedure</h2>
<table><tr><th>Parameter</th><th>Meaning</th></tr>
<tr><td>Channel threshold</td><td>Channels start where <code>S<sup>m</sup>·A<sup>n</sup> ≥ T</code> (slope × √contributing area, upslope maximum), default T = 50 (m = 1, n = 0.5).
As in TauDEM, <b>A is counted in cells</b>, so T depends on the cell size. Lower = denser network; calibrate it on the observed channel heads (e.g. 8 for a 10 m DTM in the Avisio test).</td></tr>
<tr><td>Cell size from DTM</td><td>Untick to override the cell size.</td></tr>
<tr><td>Kernel density radius</td><td>Search radius (m) of the quartic (Silverman) kernel used for the initiation-point density. Default 50 m.</td></tr>
<tr><td>Fill depressions</td><td>Optional pre-processing, identical to ArcGIS <i>Fill</i>. The procedure itself always applies TauDEM PitRemove.</td></tr>
<tr><td>Save intermediate rasters</td><td>Also writes <code>fel, p, slp, sd8, ad8, sa, ssa, src, inDF</code>.</td></tr></table>

<a name="advanced"></a><h2>Advanced · DTM resolution and custom thresholds</h2>
<div class="warn"><b>Read before changing these values.</b> The defaults reproduce the original Procedura DF (Cavalli et al., 2017). Its thresholds
(initiation curve <code>S &gt; 0.32·A<sup>−0.2</sup></code>, classes at 8° and 3°, 38° upper limit) come from literature based on DTMs of about
<b>10 m</b> resolution, <b>not LiDAR</b>: Horton et al. (2013) consider a 10 m DEM a good compromise, after Zhang &amp; Montgomery (1994) and Quinn et al. (1995).
The slopes they refer to — above all the non-linear area–slope initiation curve — are <b>reach-scale</b> channel slopes, not the very local slope of a
boulder, a step or a vertical drop. A very fine DTM (e.g. 0.5–2.5 m LiDAR) inevitably resolves such features and alters slopes, classes and the
representativeness of the thresholds (Vianello et al., 2009; Kienzle, 2004). With fine DTMs consider <b>generalizing the DTM to 5–10 m</b>, and change
the thresholds only after a calibration on field data.</div>
<h3>DTM generalization (pre-processing)</h3>
<p>Tick the group in the <b>Advanced</b> tab, set the <b>target cell size</b> (larger than the DTM cell) and the method. The DTM is aggregated first;
fill, flow directions and the whole procedure then run on the generalized DTM, saved as <code>DTM_generalized.tif</code>.</p>
<table><tr><th>Method</th><th>Use</th></tr>
<tr><td>average</td><td>area-weighted mean of the input cells — the standard aggregation (recommended)</td></tr>
<tr><td>median</td><td>median of the input cells centred in the new cell: robust to spikes, residual vegetation/buildings and isolated boulders</td></tr>
<tr><td>bilinear, cubic</td><td>smooth GDAL interpolators (cubic can slightly overshoot)</td></tr></table>
<p class="sub">average and median are computed by DFCC itself and give the same result everywhere (stand-alone, pip, QGIS, ArcGIS).</p>
<p><b>Rescale the channel threshold</b> (on by default): A is counted in cells, so the threshold is multiplied by <code>(old cell / new cell)<sup>2n</sup></code>
to keep the same <code>S<sup>m</sup>·A<sup>n</sup></code> with A in m² (50 at 2.5 m → 12.5 at 10 m). The network still changes with resolution: check it.</p>
<h3>Custom thresholds</h3>
<table><tr><th>Setting</th><th>Default</th><th>Meaning</th></tr>
<tr><td>Slope exponent m, area exponent n</td><td>1, 0.5</td><td>Channel extraction on <code>S<sup>m</sup>·A<sup>n</sup></code></td></tr>
<tr><td>Initiation coefficient k, exponent e</td><td>0.32, −0.2</td><td>Initiation where <code>S &gt; k·A<sup>e</sup></code>, A in km²</td></tr>
<tr><td>Max initiation area</td><td>20 km²</td><td>No initiation above this contributing area</td></tr>
<tr><td>Propagation / slowing</td><td>0.1405 (8°)</td><td>Boundary between classes 1 and 3</td></tr>
<tr><td>Slowing / stop</td><td>0.0524 (3°)</td><td>Boundary between classes 3 and 4</td></tr>
<tr><td>Max slope classified</td><td>0.7812 (38°)</td><td>Steeper cells are not classified</td></tr></table>
<p>Slopes are tangents (m/m); the equivalent angle is shown next to each box. Inconsistent values are refused
(<code>0 &lt; stop &lt; slowing &lt; max slope</code>). When any value differs from the default the tab shows <b>●</b>, the console lists the custom values and
they are stored in the JSON configuration: the result is <i>not</i> the standard Procedura DF. <b>Reset to defaults</b> restores everything.</p>

<a name="classes"></a><h2>Channel classes</h2>{img("classes.png", 640)}
<p class="sub">Default thresholds below; all of them can be changed in the <a href="#advanced">Advanced</a> tab.</p>
<table><tr><th>Value</th><th>Class</th><th>Colour</th><th>Condition (S = D∞ slope, A = area in km²)</th></tr>
<tr><td>1</td><td>Propagation</td><td style="color:#1f5fbf">blue</td><td>all other channel cells</td></tr>
<tr><td>2</td><td>Initiation</td><td style="color:#d62828">red</td><td><code>S &gt; 0.32·A<sup>−0.2</sup></code> and A &lt; 20 km²</td></tr>
<tr><td>3</td><td>Slowing</td><td style="color:#f77f00">orange</td><td><code>0.0524 &lt; S &lt; 0.1405</code></td></tr>
<tr><td>4</td><td>Stop</td><td style="color:#2a9d3c">green</td><td><code>S &lt; 0.0524</code></td></tr></table>

<a name="density"></a><h2>Initiation density and high-density areas</h2>
<p>Every initiation cell (class 2) becomes a point (cell centre). The <b>kernel density</b> (points/ha) is computed over the whole DTM.
<b>High-density areas</b> are the upper class of a 2-class <b>natural-breaks (Fisher–Jenks)</b> classification of the non-zero density values; they outline the areas
with the highest topographic initiation potential (<code>HighDensity.shp</code>).</p>
{img("map_overview.png", 560)}

<a name="part2"></a><h2>3 · Main channels and runout</h2>
<table><tr><th>Parameter</th><th>Meaning</th></tr>
<tr><td>Min / Max basin area</td><td>Basins are the network outlets with area inside this range (default 1–20 km², the validity range of the procedure).</td></tr>
<tr><td>Split at confluences</td><td>A confluence whose two branches both exceed this area (default 2 km²) separates two basins (e.g. Gadria and Strimm).</td></tr>
<tr><td>Pour points</td><td>Optional point shapefile: use these outlets instead of the automatic selection (snapped to the network within 50 m).</td></tr>
<tr><td>Main channel</td><td><b>largest contributing area</b> (default): at each confluence going upstream follow the branch with the largest area – keeps the real geomorphic channel;
<b>longest upstream path</b>: can leave the main concavity; <b>highest source</b>: from the highest channel head, down to the outlet.</td></tr>
<tr><td>Energy factor</td><td>The flow stops when <code>K &gt; factor · L</code> (default 0.4).</td></tr>
<tr><td>Spurious restart &lt;</td><td>A restart that dies within this length (default 30 m) is flagged <i>spurious</i>.</td></tr>
<tr><td>Extend past outlet</td><td>Continues the profile downstream beyond the basin outlet along the network (metres), e.g. over an alluvial fan. 0 = off.</td></tr>
<tr><td>Whole network runout</td><td>Off by default. Besides the main channel, the energy rule is applied to <b>every channel cell</b> of the selected basins (and the extension below the outlets), walking downstream. At confluences the <b>locally worst condition</b> is propagated: among the flowing branches the one with the largest energy margin <code>0.4·L − K</code> (envelope, never a sum). A flowing tributary re-activates a stopped trunk. It is drawn with the same colours as the main-channel runout (see <i>Runout colours</i> below), thinner and on top of it. Outputs: <code>Runout_network.shp</code> (field <i>main</i> = 1 on main-channel links), <code>Runout_network_events.shp</code> and <code>net_*</code> summary columns. The main-channel results are unchanged.</td></tr>
<tr><td>Start at head</td><td>Starts the energy balance at the channel head even without an initiation cell.</td></tr>
<tr><td>Initiation points for MSF, Point snap, Prune</td><td>See below.</td></tr></table>
<h3>Runout colours (main channel and whole network)</h3>
<table><tr><th>Colour</th><th>Meaning</th></tr>
<tr><td><span style="color:#ffd60a">■</span> yellow</td><td>channel not yet activated (upstream of the first initiation)</td></tr>
<tr><td><span style="color:#e63946">▲</span> red</td><td>initiation (▼ lighter red = restart; grey × = spurious restart)</td></tr>
<tr><td><span style="color:#1f6feb">■</span> blue</td><td>runout: the flow continues</td></tr>
<tr><td><span style="color:#f77f00">■</span> orange</td><td>stop (intermediate stop marker)</td></tr>
<tr><td><span style="color:#6ec6ff">■</span> light blue</td><td>stopped, but the flow resumes further downstream (a restart, or re-activation by a lateral)</td></tr>
<tr><td><span style="color:#2a9d3c">■</span> green</td><td>after the final stop (final stop marker = green X on the main channel)</td></tr>
<tr><td><span style="color:#8e44ad">◆</span> purple</td><td>final stop on a lateral (whole network only)</td></tr>
<tr><td><span style="color:#c2185b">✚</span> magenta</td><td>final stop on the main channel caused by the energy of a lateral (whole network only)</td></tr></table>
<p>A <b>final stop</b> on the main channel is a stop after which no flow (restart or re-activation by a lateral) occurs downstream on the main channel.
On a lateral it is a stop with no restart before the lateral joins the main channel. Many final stops on laterals are normal. The legend is shown beside the map.</p>
{img("map_runout.png", 560)}

<a name="rule"></a><h2>Runout energy rule</h2>{img("runout_rule.png", 620)}
<p>Going downstream along the main channel: <b>L</b> = cumulative elevation drop on class 1–2 cells; <b>K</b> = cumulative distance on class 3–4 cells.
The flow <b>stops</b> at the first cell where <code>K &gt; 0.4·L</code>. At the next initiation cell it <b>restarts</b> (L and K reset). A restart that dies within the
<i>spurious restart</i> length is flagged. The <b>final stop</b> is the last stop not followed by a valid restart; if the flow reaches the end of the profile there is none.
<code>DF_YN</code>: 1 no flow, 2 stop, 3 flow.</p>{img("profile.png", 640)}

<a name="msf"></a><h2>MSF initiation points</h2>
<p>For every high-density area DFCC finds the network cells inside it (or within <i>Point snap</i> metres) and, for each local network piece, climbs the branch with the largest area to its
head: the point is snapped on the network. <b>Prune</b> keeps only the highest of several aligned points (a point lying on the downstream flow path of a higher kept point is
dropped; <code>keep = 0</code>, <code>dropped_by</code> gives the covering point). Use <code>InitiationPoints_MSF.shp</code> as input for MSF-type models.</p>

<a name="outputs"></a><h2>Output files</h2>
<table><tr><th>File</th><th>Content</th></tr>
<tr><td><code>ClassifiedNetwork.tif</code></td><td>Classes 1–4 on the channel network</td></tr>
<tr><td><code>InitiationDensity.tif</code></td><td>Kernel density of initiation points (points/ha)</td></tr>
<tr><td><code>Network3D.shp</code></td><td>Channel arcs with elevation (ESRI-equivalent geometry)</td></tr>
<tr><td><code>Network_classes.shp</code></td><td>Network split by class (ready for symbology; field <code>class</code>)</td></tr>
<tr><td><code>HighDensity.tif / .shp</code></td><td>High-density areas (raster and polygons)</td></tr>
<tr><td><code>Runout_mainchannel.shp</code></td><td>Main channel split by class and flow state</td></tr>
<tr><td><code>Runout_events.shp</code></td><td>Initiation, stops, restarts, spurious restarts, final stop</td></tr>
<tr><td><code>Runout_points.shp</code></td><td>Point profile with ClassNet, DF_YN, L, K, cumulative distance</td></tr>
<tr><td><code>Runout_summary.csv</code></td><td>One row per basin: area, 2-D and 3-D length, stops, final stop distance…</td></tr>
<tr><td><code>InitiationPoints_MSF.shp / _candidates.shp</code></td><td>Kept points / all candidate points</td></tr></table>

<a name="cli"></a><h2>Command line and configuration</h2>
<p>The same engine runs without the GUI (the executable accepts the same commands):</p>
<p><code>dfcc run dtm.tif -o out --runout</code><br><code>dfcc run dtm.tif -o out -t 8 --pour-points outlet.shp --extend-polygon fan.shp</code><br>
<code>dfcc run --config cfg.json -o out2</code><br><code>dfcc run lidar.tif -o out --generalize 10 --generalize-method median</code><br>
<code>dfcc run dtm.tif -o out --s-slow 0.1763 --s-stop 0.0699</code> (classes at 10° and 4°)<br><code>dfcc fill dtm.tif filled.tif</code> · <code>dfcc run --help</code></p>

<a name="plugins"></a><h2>QGIS · ArcGIS · pip · executable</h2>
<table><tr><th>Where</th><th>How</th></tr>
<tr><td>pip</td><td><code>pip install "dfcc[gui] @ git+https://github.com/HydrogeomorphologyTools/DFCC"</code> (without <code>[gui]</code>: command line only) – commands <code>dfcc</code> and <code>dfcc-gui</code>.</td></tr>
<tr><td>QGIS ≥ 3.22</td><td>Copy <code>qgis_plugin/dfcc_qgis</code> into the QGIS plugins folder; the algorithm appears in <i>Processing → DFCC</i>. It uses the python package, or the executable (variable <code>DFCC_EXE</code>).</td></tr>
<tr><td>ArcGIS Pro</td><td>Add <code>arcgis_toolbox/DFCC.pyt</code> (python package or <code>DFCC_EXE</code>). ArcMap 10.x (Python 2.7): use the GUI/CLI.</td></tr>
<tr><td>Executable</td><td><code>DFCC.exe</code>: no arguments = this GUI; with arguments = command line.</td></tr></table>

<a name="tips"></a><h2>Tips and troubleshooting</h2>
<ul><li>The <b>first run</b> in a fresh installation compiles the numerical code (~1 min); results are then cached.</li>
<li>No network or a very sparse one → lower the <i>channel threshold</i> (the right value depends on the cell size).</li>
<li>The main channel ends before the fan → the DTM is cut at a narrow neck, or use <i>Extend past outlet</i> / a pour point.</li>
<li>Natural-breaks threshold differs slightly from ArcGIS → ArcGIS approximates Jenks on a sample; DFCC solves it exactly (difference ≈ 0.2 % in within-class variance).</li>
<li>Very large DTMs need memory (roughly 200 bytes per cell).</li></ul>

<a name="about"></a><h2>About</h2>
<p><b>DFCC {__version__}</b> – Debris-Flow Channel Classification<br>
<b>Authors:</b> Stefano Crema (contact: stefano.crema@cnr.it), Marco Cavalli, Alessandro Sarretta – CNR GEO, 2026.<br>Source code, issues and releases: <a href="https://github.com/HydrogeomorphologyTools/DFCC">github.com/HydrogeomorphologyTools/DFCC</a> · version {__version__} is a <i>testing</i> release.</p>
<p>GPL-2.0-or-later · D8 / D∞ routines derive from the native rewrites of <i>SedInConnect 3.2</i> (HydrogeomorphologyTools), themselves ports of TauDEM (D. Tarboton).
Method: <i>Procedura DF</i> (Cavalli, Crema, Viero, Marchi – CNR). Details in <code>docs/METHOD.md</code>.</p>
<h3>Bibliography</h3>
<p>Cavalli, M., Crema, S., Trevisani, S., Marchi, L. (2017). GIS tools for preliminary debris-flow assessment at regional scale.
<i>Journal of Mountain Science</i> 14(12), 2498–2510. <a href="https://doi.org/10.1007/s11629-017-4573-y">doi:10.1007/s11629-017-4573-y</a></p>
<p>If you use DFCC, please cite the paper above and this software (Crema, Cavalli, Sarretta, 2026).</p>
<p class="sub">Cited in this Help (complete list with the sources of every threshold in the README and in <code>docs/METHOD.md</code>):</p>
<ul class="sub">
<li>Horton, P., Jaboyedoff, M., Rudaz, B., Zimmermann, M. (2013). Flow-R, a model for susceptibility mapping of debris flows and other gravitational hazards at a regional scale. <i>Nat. Hazards Earth Syst. Sci.</i> 13(4), 869–885. doi:10.5194/nhess-13-869-2013</li>
<li>Kienzle, S. (2004). The effect of DEM raster resolution on first order, second order and compound terrain derivatives. <i>Transactions in GIS</i> 8(1), 83–111. doi:10.1111/j.1467-9671.2004.00169.x</li>
<li>Quinn, P.F., Beven, K.J., Lamb, R. (1995). The ln(a/tan β) index: how to calculate it and how to use it within the TOPMODEL framework. <i>Hydrol. Process.</i> 9(2), 161–182. doi:10.1002/hyp.3360090204</li>
<li>Vianello, A., Cavalli, M., Tarolli, P. (2009). LiDAR-derived slopes for headwater channel network analysis. <i>Catena</i> 76(2), 97–106. doi:10.1016/j.catena.2008.09.012</li>
<li>Zhang, W., Montgomery, D.R. (1994). Digital elevation model grid size, landscape representation, and hydrologic simulations. <i>Water Resour. Res.</i> 30(4), 1019–1028. doi:10.1029/93WR03553</li></ul>
</body></html>"""


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DFCC – Help")
        self.resize(1080, 760)
        lay = QHBoxLayout(self)
        sp = QSplitter()
        self.setStyleSheet("QDialog{background:#0b1620;} QListWidget{background:#13222f;color:#e8f1f7;border:1px solid #26405a;font-size:10.5pt;padding:4px;}"
                           "QListWidget::item{padding:5px 8px;} QListWidget::item:selected{background:#2b6f99;color:white;}"
                           "QTextBrowser{background:#0e1a24;color:#e8f1f7;border:1px solid #26405a;}")
        self.nav = QListWidget()
        self.nav.setMaximumWidth(230)
        for key, title in SECTIONS:
            self.nav.addItem(title)
        self.view = QTextBrowser()
        self.view.setSearchPaths([str(HELP_DIR)])
        self.view.setOpenExternalLinks(True)
        self.view.setHtml(html())
        sp.addWidget(self.nav); sp.addWidget(self.view)
        sp.setStretchFactor(1, 1)
        lay.addWidget(sp)
        self.nav.currentRowChanged.connect(lambda i: self.view.scrollToAnchor(SECTIONS[i][0]))
        self.nav.setCurrentRow(0)
