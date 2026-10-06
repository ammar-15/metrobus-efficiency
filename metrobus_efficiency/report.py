"""Write the summary, CSVs and GeoJSON for the plan."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import Config
from .gtfs import Feed
from .metrics import nearest_stop_walk_m
from .network import Network
from .plan import Line


def stop_plan(feed: Feed, net: Network, trunks: list[Line], feeders: list[Line]) -> pd.DataFrame:
    trunk_stop = {}
    for t in trunks:
        for s in t.stops:
            trunk_stop.setdefault(s, []).append(t.name)
    on_trunk_path = {n for t in trunks for n in t.path}
    feeder_stop = {}
    for f in feeders:
        for s in f.stops[1:]:
            feeder_stop.setdefault(s, []).append(f.name)
    all_trunk_stops = sorted(trunk_stop)

    rows = []
    for s in feed.stops.itertuples():
        n = net.stop_to_node[s.stop_id]
        if n in trunk_stop:
            status, lines = "trunk stop", trunk_stop[n] + feeder_stop.get(n, [])
        elif n in feeder_stop:
            status, lines = "feeder stop", feeder_stop[n]
        elif n in on_trunk_path:
            status, lines = "removed (trunk passes, stop consolidated)", []
        else:
            status, lines = "walk to nearby stop", []
        rows.append(
            {
                "stop_id": s.stop_id,
                "stop_name": s.stop_name,
                "lat": s.lat,
                "lon": s.lon,
                "status": status,
                "lines": ", ".join(lines),
                "walk_to_trunk_m": round(nearest_stop_walk_m(net, n, all_trunk_stops)),
            }
        )
    return pd.DataFrame(rows)


def geojson(net: Network, hubs: list[int], lines: list[Line], cfg: Config) -> dict:
    feats = []
    for ln in lines:
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "line": ln.name,
                    "type": ln.kind,
                    "headway_min": ln.headway_min,
                    "run_min": round(ln.run_min, 1),
                    "buses": ln.buses(cfg),
                    "flags": ln.flags,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[float(net.nodes.at[n, "lon"]), float(net.nodes.at[n, "lat"])] for n in ln.path],
                },
            }
        )
    for h in hubs:
        feats.append(
            {
                "type": "Feature",
                "properties": {"hub": str(net.nodes.at[h, "name"])},
                "geometry": {"type": "Point", "coordinates": [float(net.nodes.at[h, "lon"]), float(net.nodes.at[h, "lat"])]},
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def write_summary(path: Path, cur: dict, prop: dict, lines_df: pd.DataFrame, net: Network, hubs: list[int], cfg: Config) -> None:
    def delta(a, b):
        return f"{b - a:+,.0f}" if isinstance(a, (int, float)) else ""

    comp = pd.DataFrame(
        [
            ["Peak buses in service", cur["peak_buses"], prop["peak_buses"], delta(cur["peak_buses"], prop["peak_buses"])],
            ["Weekday revenue hours", cur["weekday_revenue_hours"], prop["weekday_revenue_hours"], delta(cur["weekday_revenue_hours"], prop["weekday_revenue_hours"])],
            ["Places with frequent service (≈15 min or better)", f"{cur['frequent_places_pct']}%", f"{prop['frequent_places_pct']}%", ""],
            ["Bus activity at frequent places", f"{cur['frequent_activity_pct']}%", f"{prop['frequent_activity_pct']}%", ""],
        ],
        columns=["", "Today", "Proposed", "Change"],
    )
    hub_list = "\n".join(f"{i + 1}. {net.nodes.at[h, 'name']} ({net.nodes.at[h, 'departures']} buses/weekday today)" for i, h in enumerate(hubs))
    unserved = prop["unserved_places"]
    text = f"""# Metrobus trunk-and-feeder plan

Generated from the Metrobus GTFS schedule for **{cur['service_date']}** (busiest weekday in the feed).
Today: {cur['routes']} routes, {cur['weekday_trips']:,} weekday trips, {cur['stops']:,} stops
(grouped into {cur['places']:,} places after merging paired stops across the street).

## Today vs proposed

{_md_table(comp)}

Proposed: **{prop['trunk_lines']} trunk lines** every {cfg.trunk_headway_min:g} min and
**{prop["feeder_loops"]} feeder lines** every {cfg.feeder_headway_min:g} min,
running {cfg.service_hours_per_weekday:g} h per weekday. {prop['served_places_pct']}% of today's places stay served
by a trunk stop within {cfg.trunk_catchment_m:g} m or a feeder stop.

## Hubs

{hub_list}

## Lines

{_md_table(lines_df.drop(columns=['flags']))}

{"### Flags" if (lines_df['flags'] != '').any() else ""}
{chr(10).join(f"- **{r.line}**: {r.flags}" for r in lines_df.itertuples() if r.flags)}

{f"{len(unserved)} places are left without service; see `stops_plan.csv` (status 'walk to nearby stop')." if unserved else ""}

## How to read this

- *Peak buses today* counts trips running at the same moment, a lower bound on today's fleet in service.
- Trunk running times come from today's scheduled times between stops, minus {cfg.dwell_saving_s:g} s for every stop
  removed by consolidating to ~{cfg.trunk_stop_spacing_m:g} m spacing. No bus lanes or signal priority are assumed.
- Feeder lines follow today's routes where they serve stops away from the trunks, and end at a trunk stop so riders can transfer.
- This is a planning sketch from schedule data, not ridership. It shows where frequency could go for a similar
  number of buses; real proposals need boarding counts, street checks and public input.
"""
    path.write_text(text.replace("\n\n\n", "\n\n"))


def write_outputs(out_dir: Path, feed: Feed, net: Network, hubs, trunks, feeders, cur, prop, lines_df, cfg: Config) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines_df.to_csv(out_dir / "lines.csv", index=False)
    stop_plan(feed, net, trunks, feeders).to_csv(out_dir / "stops_plan.csv", index=False)
    (out_dir / "network.geojson").write_text(json.dumps(geojson(net, hubs, trunks + feeders, cfg)))
    (out_dir / "metrics.json").write_text(
        json.dumps({"current": cur, "proposed": {k: v for k, v in prop.items() if k != "unserved_places"}}, indent=2)
    )
    write_summary(out_dir / "summary.md", cur, prop, lines_df, net, hubs, cfg)
