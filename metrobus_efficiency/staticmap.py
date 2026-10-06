"""A static PNG of the plan (no basemap), handy for slides, READMEs and council submissions."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .config import Config  # noqa: E402
from .mapviz import FEEDER_COLORS, TRUNK_COLORS  # noqa: E402
from .network import Network  # noqa: E402
from .plan import Line  # noqa: E402


def build_png(net: Network, hubs: list[int], trunks: list[Line], feeders: list[Line], cfg: Config, out: Path) -> Path:
    lat0 = float(net.nodes["lat"].mean())
    k = math.cos(math.radians(lat0))

    def xy(nodes):
        return [float(net.nodes.at[n, "lon"]) * k for n in nodes], [float(net.nodes.at[n, "lat"]) for n in nodes]

    fig, ax = plt.subplots(figsize=(11, 11), dpi=150)
    for u, v, d in net.graph.edges(data=True):
        if not d.get("synthetic"):
            x, y = xy([u, v])
            ax.plot(x, y, color="#c9cdd2", lw=0.8, zorder=1)

    for i, f in enumerate(feeders):
        x, y = xy(f.path)
        c = FEEDER_COLORS[i % len(FEEDER_COLORS)]
        ax.plot(x, y, color=c, lw=2, ls=(0, (4, 3)), zorder=2)
        sx, sy = xy(f.stops[1:])
        ax.scatter(sx, sy, s=10, color=c, zorder=3)

    for i, t in enumerate(trunks):
        x, y = xy(t.path)
        c = TRUNK_COLORS[i % len(TRUNK_COLORS)]
        ax.plot(x, y, color=c, lw=4.5, solid_capstyle="round", zorder=4, label=f"{t.name}  every {t.headway_min:g} min")
        sx, sy = xy(t.stops)
        ax.scatter(sx, sy, s=18, color="white", edgecolor=c, linewidth=1.2, zorder=5)

    hx, hy = xy(hubs)
    ax.scatter(hx, hy, s=170, marker="*", color="black", zorder=6)
    for h, x, y in zip(hubs, hx, hy):
        ax.annotate(str(net.nodes.at[h, "name"]), (x, y), xytext=(6, 6), textcoords="offset points", fontsize=8,
                    weight="bold", zorder=7, bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))

    ax.plot([], [], color="#999", lw=2, ls=(0, (4, 3)), label=f"Feeder lines  every {cfg.feeder_headway_min:g} min")
    ax.plot([], [], color="#c9cdd2", lw=1, label="Today's network")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8, frameon=False)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Metrobus: trunk lines between hubs + feeder lines", fontsize=12)
    for s in ax.spines.values():
        s.set_visible(False)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out
