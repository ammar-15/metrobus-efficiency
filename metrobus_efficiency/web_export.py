"""Export today's routes and several proposed plans as one JSON file for the web map.

The web map recomputes buses, service hours, cost and coverage in the browser
as people change frequencies or add/remove stops, so everything it needs to do
that lives in this file.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from .config import Config
from .gtfs import Feed
from .metrics import current_metrics
from .network import Network, route_patterns
from .plan import Line, build_feeders, build_trunks, pick_hubs

# Metrobus 2025 figures (December 2025 financial statements and the statistics page),
# used to turn modelled weekday hours into a rough annual cost.
ANNUAL_REVENUE_HOURS_2025 = 156_004
COST_PER_REVENUE_HOUR_2025 = 146.52
ANNUAL_RIDERSHIP_2025 = 4_933_118

SCENARIOS = [
    # id, label, hub count, trunk headway, feeder headway
    ("p6", "6 hubs", 6, 10, 20),
    ("p8", "8 hubs", 8, 10, 20),
    ("p10", "10 hubs", 10, 10, 20),
    ("p12", "12 hubs", 12, 10, 20),
]


def _km(net: Network, path: list[int]) -> float:
    return sum(net.dist_m(u, v) for u, v in zip(path, path[1:])) / 1000


def _round_headway(h: float) -> float:
    for nice in (5, 6, 7.5, 10, 12, 15, 20, 30, 40, 45, 60, 90, 120):
        if h <= nice * 1.08:
            return float(nice)
    return float(round(h))


def today_routes(feed: Feed, net: Network) -> list[dict]:
    st = feed.stop_times.merge(feed.trips[["trip_id", "route_id", "route_short_name"] + (["direction_id"] if "direction_id" in feed.trips.columns else [])], on="trip_id")
    if "direction_id" not in st.columns:
        st["direction_id"] = ""
    st["node"] = st["stop_id"].map(net.stop_to_node)
    st = st.dropna(subset=["node"])
    st["node"] = st["node"].astype(int)

    trips = st.sort_values(["trip_id", "stop_sequence"]).groupby("trip_id").agg(
        route_id=("route_id", "first"),
        name=("route_short_name", "first"),
        direction=("direction_id", "first"),
        nodes=("node", tuple),
        start=("dep", "min"),
        end=("arr", "max"),
    )
    trips["run"] = (trips["end"] - trips["start"]) / 60

    long_names = {}
    if "route_long_name" in feed.routes.columns:
        long_names = dict(zip(feed.routes["route_id"], feed.routes["route_long_name"]))
    colors = {}
    if "route_color" in feed.routes.columns:
        colors = {r: c for r, c in zip(feed.routes["route_id"], feed.routes["route_color"]) if c}

    out = []
    for rid, grp in trips.groupby("route_id"):
        dirs = []
        for d, g in grp.groupby("direction"):
            pattern, n = Counter(g["nodes"]).most_common(1)[0]
            dirs.append(
                {
                    "dir": d,
                    "pattern": list(pattern),
                    "run": float(g.loc[g["nodes"] == pattern, "run"].median()),
                    "trips": int(len(g)),
                    "start": float(g["start"].min()),
                    "end": float(g["end"].max()),
                    "g": g,
                }
            )
        dirs.sort(key=lambda x: -x["trips"])
        main = dirs[0]
        # Midday headway in the busier direction; fall back to the all-day average.
        g = main["g"]
        mid = g[(g["start"] >= 10 * 3600) & (g["start"] < 15 * 3600)]
        if len(mid) >= 2:
            headway = 300 / len(mid)
        else:
            span_min = (main["end"] - main["start"]) / 60
            headway = span_min / max(main["trips"] - 1, 1)
        is_loop = len(dirs) == 1 or main["pattern"][0] == main["pattern"][-1]
        cycle = main["run"] if is_loop else main["run"] + dirs[1]["run"]
        span_h = (max(d["end"] for d in dirs) - min(d["start"] for d in dirs)) / 3600
        actual_hours = float((grp["end"] - grp["start"]).sum() / 3600)

        path = main["pattern"]
        name = str(grp["name"].iloc[0])
        out.append(
            {
                "id": f"r{rid}",
                "name": name,
                "long_name": str(long_names.get(rid, "")),
                "kind": "route",
                "color": f"#{colors[rid]}" if rid in colors else None,
                "path": [int(n) for n in path],
                "stop_idx": list(range(len(path))),
                "run_min": round(main["run"], 1),
                "cycle_min": round(max(cycle, 1.0), 1),
                "headway_min": _round_headway(headway),
                "span_h": round(span_h, 2),
                "km": round(_km(net, path), 2),
                "actual_trips": int(len(grp)),
                "actual_hours": round(actual_hours, 1),
            }
        )
    out.sort(key=lambda r: (len(r["name"]), r["name"]))
    return out


def _line_dict(ln: Line, net: Network, cfg: Config, hub_names: dict[int, str]) -> dict:
    path = [int(n) for n in ln.path]
    stop_set = list(ln.stops)
    stop_idx: list[int] = []
    j = 0
    for s in stop_set:  # stops appear along the path in order
        while j < len(path) and path[j] != s:
            j += 1
        if j < len(path):
            stop_idx.append(j)
            j += 1
    if ln.kind == "trunk":
        label = " – ".join(hub_names[h] for h in (ln.hubs[0], ln.hubs[-1]))
        via = [hub_names[h] for h in ln.hubs[1:-1]]
    else:
        a, b = (str(net.nodes.at[n, "name"]) for n in (path[0], path[-1]))
        label = f"Loop from {a}" if path[0] == path[-1] else f"{a} – {b}"
        meets = [str(net.nodes.at[n, "name"]) for n in ln.hubs]
        via = []
        note = f"Follows today's route {ln.source}" if ln.source else ""
        if meets:
            note += f", meets the trunk lines at {' and '.join(dict.fromkeys(meets))}."
        else:
            note += "."

    if ln.kind == "trunk":
        note = ""
    return {
        "id": ln.name.lower(),
        "note": note.strip(", "),
        "name": ln.name,
        "long_name": label,
        "via": via,
        "kind": ln.kind,
        "color": None,
        "path": path,
        "stop_idx": stop_idx,
        "run_min": round(ln.run_min, 1),
        "cycle_min": round(ln.cycle_min, 1),
        "headway_min": ln.headway_min,
        "span_h": cfg.service_hours_per_weekday,
        "km": round(_km(net, path), 2),
        "hub": int(ln.hub) if ln.hub is not None else None,
        "source": ln.source,
        "hubs": [int(h) for h in ln.hubs],
        "flags": ln.flags,
    }


def build_web_data(feed: Feed, net: Network, cfg: Config) -> dict:
    cur = current_metrics(feed, net)
    nodes = net.nodes
    places = [
        {
            "id": int(n),
            "name": str(r["name"]),
            "lat": round(float(r.lat), 6),
            "lon": round(float(r.lon), 6),
            "deps": int(r["departures"]),
            "routes": [str(x) for x in r["routes"]],
        }
        for n, r in nodes.iterrows()
    ]

    scenarios = [
        {
            "id": "today",
            "label": "Today",
            "description": f"Metrobus routes as scheduled on {feed.service_date.isoformat()}, at their midday frequency.",
            "hubs": [],
            "lines": today_routes(feed, net),
        }
    ]
    patterns = route_patterns(feed, net)
    seen_hub_sets: set[tuple[int, ...]] = set()
    for sid, label, n_hubs, th, fh in SCENARIOS:
        c = copy.copy(cfg)
        c.n_hubs = n_hubs
        c.hub_min_share = min(cfg.hub_min_share, 0.04)
        c.trunk_headway_min = th
        c.feeder_headway_min = fh
        hubs = pick_hubs(net, c)
        key = tuple(sorted(hubs))
        if key in seen_hub_sets:  # fewer real hubs than asked for: same plan as before
            continue
        seen_hub_sets.add(key)
        label = f"{len(hubs)} hubs"
        trunks, _ = build_trunks(net, hubs, c)
        feeders, _ = build_feeders(net, hubs, trunks, c, patterns)
        hub_names = {h: str(nodes.at[h, "name"]) for h in hubs}
        scenarios.append(
            {
                "id": sid,
                "label": label,
                "description": (
                    f"{len(trunks)} trunk lines every {th} min between {len(hubs)} hubs, "
                    f"plus {len(feeders)} feeder loops every {fh} min."
                ),
                "hubs": [int(h) for h in hubs],
                "lines": [_line_dict(l, net, c, hub_names) for l in trunks + feeders],
            }
        )

    # Background: every street link buses use today.
    edges = [[int(u), int(v)] for u, v, d in net.graph.edges(data=True) if not d.get("synthetic")]

    return {
        "generated": pd.Timestamp.now(tz="America/St_Johns").isoformat(timespec="minutes"),
        "service_date": feed.service_date.isoformat(),
        "today_actual": {
            "routes": cur["routes"],
            "weekday_trips": cur["weekday_trips"],
            "weekday_revenue_hours": cur["weekday_revenue_hours"],
            "peak_buses": cur["peak_buses"],
            "stops": cur["stops"],
        },
        "constants": {
            "annual_revenue_hours_2025": ANNUAL_REVENUE_HOURS_2025,
            "cost_per_revenue_hour_2025": COST_PER_REVENUE_HOUR_2025,
            "annual_ridership_2025": ANNUAL_RIDERSHIP_2025,
            # Annual hours per scheduled weekday hour (covers weekends and holidays at lower service).
            "annual_factor": round(ANNUAL_REVENUE_HOURS_2025 / max(cur["weekday_revenue_hours"], 1), 2),
        },
        "defaults": {
            "layover_factor": cfg.layover_factor,
            "dwell_s": 20,
            "detour_factor": 1.3,
            "walk_m": cfg.trunk_catchment_m,
            "frequent_min": 15,
            "service_hours": cfg.service_hours_per_weekday,
        },
        "places": places,
        "edges": edges,
        "scenarios": scenarios,
    }


def write_web_data(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")))
    return path
