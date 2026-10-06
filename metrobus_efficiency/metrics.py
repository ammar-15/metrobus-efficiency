"""Compare today's schedule with the proposed trunk-and-feeder network."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Config
from .gtfs import Feed
from .network import Network, haversine
from .plan import Line, served_by_trunks

FREQUENT_BUSES_PER_HOUR = 8  # both directions combined, ~every 15 min each way


@dataclass
class Comparison:
    current: dict
    proposed: dict
    lines: pd.DataFrame


def current_metrics(feed: Feed, net: Network) -> dict:
    st = feed.stop_times
    span = st.groupby("trip_id").agg(start=("dep", "min"), end=("arr", "max"))
    rev_hours = float((span["end"] - span["start"]).clip(lower=0).sum() / 3600)

    # Peak buses in service = most trips running at the same moment (a lower bound on fleet).
    ev = pd.concat([pd.Series(1, index=span["start"]), pd.Series(-1, index=span["end"])]).sort_index(kind="stable")
    peak = int(ev.groupby(level=0).sum().cumsum().max())

    # Midday frequency at each node.
    mid = st[(st["dep"] >= 10 * 3600) & (st["dep"] < 15 * 3600)].copy()
    mid["node"] = mid["stop_id"].map(net.stop_to_node)
    per_hr = mid.groupby("node")["trip_id"].nunique() / 5.0
    freq = net.nodes.index.to_series().map(per_hr).fillna(0)
    weights = net.nodes["departures"].astype(float)
    frequent = freq >= FREQUENT_BUSES_PER_HOUR

    return {
        "service_date": feed.service_date.isoformat(),
        "routes": int(feed.trips["route_id"].nunique()),
        "weekday_trips": int(feed.trips["trip_id"].nunique()),
        "weekday_revenue_hours": round(rev_hours, 1),
        "peak_buses": peak,
        "stops": int(len(feed.stops)),
        "places": int(len(net.nodes)),
        "frequent_places_pct": round(100 * frequent.mean(), 1),
        "frequent_activity_pct": round(100 * (weights[frequent].sum() / max(weights.sum(), 1)), 1),
    }


def line_table(lines: list[Line], net: Network, cfg: Config) -> pd.DataFrame:
    rows = []
    for ln in lines:
        km = sum(net.dist_m(u, v) for u, v in zip(ln.path, ln.path[1:])) / 1000
        buses = ln.buses(cfg)
        rows.append(
            {
                "line": ln.name,
                "type": ln.kind,
                "from_to": " → ".join(str(net.nodes.at[h, "name"]) for h in ([ln.path[0], ln.path[-1]] if ln.kind == "trunk" else [ln.hub])),
                "hubs": " · ".join(str(net.nodes.at[h, "name"]) for h in ln.hubs),
                "stops": len(ln.stops),
                "km": round(km, 1),
                "run_min": round(ln.run_min, 1),
                "headway_min": ln.headway_min,
                "buses": buses,
                "weekday_hours": round(cfg.service_hours_per_weekday * ln.cycle_min / ln.headway_min, 1),
                "flags": "; ".join(ln.flags),
            }
        )
    return pd.DataFrame(rows)


def proposed_metrics(trunks: list[Line], feeders: list[Line], net: Network, cfg: Config) -> dict:
    covered_frequent = served_by_trunks(net, trunks, cfg)
    on_feeder = {n for f in feeders for n in f.path}
    served = covered_frequent | on_feeder
    weights = net.nodes["departures"].astype(float)
    total_w = max(weights.sum(), 1)
    idx = net.nodes.index
    t_buses = sum(t.buses(cfg) for t in trunks)
    f_buses = sum(f.buses(cfg) for f in feeders)
    return {
        "trunk_lines": len(trunks),
        "feeder_loops": len(feeders),
        "trunk_buses": t_buses,
        "feeder_buses": f_buses,
        "peak_buses": t_buses + f_buses,
        # Hours of buses carrying passengers (excludes layover), same basis as today's figure.
        "weekday_revenue_hours": round(
            sum(cfg.service_hours_per_weekday * ln.cycle_min / ln.headway_min for ln in trunks + feeders), 1
        ),
        "trunk_stops": len({s for t in trunks for s in t.stops}),
        "frequent_places_pct": round(100 * len(covered_frequent) / max(len(idx), 1), 1),
        "frequent_activity_pct": round(100 * weights[list(covered_frequent)].sum() / total_w, 1),
        "served_places_pct": round(100 * len(served) / max(len(idx), 1), 1),
        "unserved_places": sorted(set(idx) - served),
    }


def nearest_stop_walk_m(net: Network, node: int, stop_nodes: list[int]) -> float:
    if not stop_nodes:
        return float("inf")
    sl = net.nodes.loc[stop_nodes, "lat"].to_numpy()
    sn = net.nodes.loc[stop_nodes, "lon"].to_numpy()
    return float(np.min(haversine(net.nodes.at[node, "lat"], net.nodes.at[node, "lon"], sl, sn)))
