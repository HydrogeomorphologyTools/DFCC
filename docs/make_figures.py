"""Regenerate the figures used in README.md from the Gadria example.

    cd examples/gadria && python ../../docs/make_figures.py
"""
import os, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dfcc import pipeline, part2, viz, config

OUT = Path(__file__).resolve().parent / "images"
OUT.mkdir(exist_ok=True)
par, rp, _ = config.load("dfcc_config.json")
par.outdir = "output"
res = pipeline.run(par, log=lambda *a: None)
out = part2.analyse(res, rp, par.outdir, log=lambda *a: None)
P = viz.PALETTE


def new(figsize=(9, 7)):
    f, ax = plt.subplots(figsize=figsize, dpi=130)
    f.patch.set_facecolor(P["bg"])
    return f, ax


def save(f, ax, name, title):
    ax.set_title(title, color=P["ink"], fontsize=11)
    f.tight_layout()
    f.savefig(OUT / name, bbox_inches="tight", facecolor=f.get_facecolor())
    plt.close(f)


# 1 classified network
f, ax = new(); viz.draw_base(ax, res); viz.draw_network(ax, res, 1.2); viz.side_legend(ax, classes=True)
save(f, ax, "01_classified_network.png", "Classified channel network (Gadria, 2.5 m DTM)")
# 2 initiation density + high density areas
f, ax = new(); viz.draw_base(ax, res); viz.draw_density(ax, res, 0.7); viz.draw_high(ax, res); viz.draw_network(ax, res, 0.8, alpha=0.5)
save(f, ax, "02_initiation_density.png", "Initiation-point density (50 m kernel) and high-density areas (natural breaks)")
# 3 main channel runout
f, ax = new(); viz.draw_base(ax, res); viz.draw_network(ax, res, 1.0, alpha=0.3)
seen = viz.draw_runout(ax, out, 3.0); viz.side_legend(ax, runout=seen)
save(f, ax, "03_main_channel_runout.png", "Main channel of each basin: runout phases and events")
# 4 profile of each basin
for b in (1, 2):
    f = plt.figure(figsize=(9, 3.8), dpi=130); f.patch.set_facecolor(P["bg"])
    viz.profile_figure(f, out, b, show3d=(b == 1)); f.savefig(OUT / f"04_profile_basin{b}.png", bbox_inches="tight", facecolor=f.get_facecolor()); plt.close(f)
# 5 whole network
f, ax = new(); viz.draw_base(ax, res); viz.draw_network(ax, res, 1.0, alpha=0.25)
s1 = viz.draw_runout(ax, out, 3.4); s2 = viz.draw_network_runout(ax, out); viz.side_legend(ax, runout=s1, network=s2)
save(f, ax, "05_whole_network_runout.png", "Whole-network runout (worst-case merge at confluences)")
# 6 MSF points
f, ax = new(); viz.draw_base(ax, res); viz.draw_network(ax, res, 1.0, alpha=0.4)
g = res.grid; H = out["hotspots"]
for keep, col, lab in ((False, "#8a8f98", "dropped"), (True, "#ffd166", "kept")):
    xy = [g.xy(d["row"], d["col"]) for d in H if bool(d["keep"]) == keep]
    ax.scatter([a for a, b in xy], [b for a, b in xy], s=18, c=col, edgecolors="k", linewidths=0.4, zorder=9, label=f"candidate, {lab}")
ax.legend(loc="upper left", bbox_to_anchor=(1.015, 1), fontsize=8, facecolor=P["panel"], edgecolor=P["muted"], labelcolor=P["ink"])
save(f, ax, "06_msf_initiation_points.png", "Initiation points for MSF (aligned candidates pruned)")
# 7 profile matrix
f = plt.figure(figsize=(10, 4.2), dpi=130); f.patch.set_facecolor(P["bg"]); viz.profile_matrix(f, out, 2, True)
f.savefig(OUT / "07_profile_matrix.png", bbox_inches="tight", facecolor=f.get_facecolor()); plt.close(f)
