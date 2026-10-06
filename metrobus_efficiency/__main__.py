"""Run the whole pipeline:  python -m metrobus_efficiency"""

from __future__ import annotations

import argparse
from pathlib import Path
import time
import webbrowser

from .config import Config
from .gtfs import download_feed, load_feed
from .mapviz import build_map
from .metrics import current_metrics, line_table, proposed_metrics
from .network import build_network, route_patterns
from .plan import build_feeders, build_trunks, pick_hubs
from .report import write_outputs
from .staticmap import build_png
from .web_export import build_web_data, write_web_data


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Redesign Metrobus as trunk lines between hubs plus feeder loops.")
    ap.add_argument("--env", help="path to a .env file (default: ./.env)")
    ap.add_argument("--gtfs", help="use this local GTFS zip instead of downloading")
    ap.add_argument("--refresh", action="store_true", help="re-download the feed even if cached")
    ap.add_argument("--hubs", type=int, help="number of hubs (overrides N_HUBS)")
    ap.add_argument("--trunk-headway", type=float, help="minutes between trunk buses")
    ap.add_argument("--feeder-headway", type=float, help="minutes between feeder buses")
    ap.add_argument("--open", action="store_true", help="open the map in a browser when done")
    ap.add_argument(
        "--web",
        nargs="?",
        const="docs/data/plan.json",
        help="also write data for the editable web map (default: docs/data/plan.json)",
    )
    args = ap.parse_args(argv)

    cfg = Config.from_env(args.env)
    if args.gtfs:
        cfg.gtfs_path = args.gtfs
    if args.hubs:
        cfg.n_hubs = args.hubs
    if args.trunk_headway:
        cfg.trunk_headway_min = args.trunk_headway
    if args.feeder_headway:
        cfg.feeder_headway_min = args.feeder_headway

    t0 = time.time()
    feed = load_feed(download_feed(cfg, force=args.refresh))
    print(f"Loaded {len(feed.stops):,} stops and {feed.trips['trip_id'].nunique():,} trips for {feed.service_date}")

    net = build_network(feed, cfg)
    print(f"Network: {len(net.nodes):,} places, {net.graph.number_of_edges():,} street links")

    hubs = pick_hubs(net, cfg)
    print("Hubs: " + " | ".join(str(net.nodes.at[h, "name"]) for h in hubs))

    trunks, _ = build_trunks(net, hubs, cfg)
    patterns = route_patterns(feed, net)
    feeders, _ = build_feeders(net, hubs, trunks, cfg, patterns)
    print(f"Plan: {len(trunks)} trunk lines, {len(feeders)} feeder loops")

    cur = current_metrics(feed, net)
    prop = proposed_metrics(trunks, feeders, net, cfg)
    lines_df = line_table(trunks + feeders, net, cfg)
    write_outputs(cfg.output_dir, feed, net, hubs, trunks, feeders, cur, prop, lines_df, cfg)
    map_path = build_map(net, hubs, trunks, feeders, cfg, cfg.output_dir / "map.html")
    build_png(net, hubs, trunks, feeders, cfg, cfg.output_dir / "plan.png")
    if args.web:
        web_path = write_web_data(Path(args.web), build_web_data(feed, net, cfg))
        print(f"Web map data: {web_path} (open docs/index.html through a local server, see README)")

    print(
        f"\nPeak buses: today {cur['peak_buses']} -> proposed {prop['peak_buses']} "
        f"({prop['trunk_buses']} trunk + {prop['feeder_buses']} feeder)"
    )
    print(f"Weekday revenue hours: today {cur['weekday_revenue_hours']} -> proposed {prop['weekday_revenue_hours']}")
    print(f"Frequent-service places: today {cur['frequent_places_pct']}% -> proposed {prop['frequent_places_pct']}%")
    print(f"\nWrote {cfg.output_dir}/ (map.html, plan.png, summary.md, lines.csv, stops_plan.csv, network.geojson) in {time.time() - t0:.0f}s")
    if args.open:
        webbrowser.open(map_path.resolve().as_uri())


if __name__ == "__main__":
    main()
