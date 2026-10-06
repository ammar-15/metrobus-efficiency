"""End-to-end smoke test on a synthetic feed (no network access needed)."""

from pathlib import Path

from metrobus_efficiency.__main__ import main
from metrobus_efficiency.config import Config
from metrobus_efficiency.gtfs import load_feed
from metrobus_efficiency.network import build_network, route_patterns
from metrobus_efficiency.plan import build_feeders, build_trunks, pick_hubs, served_by_trunks

from .synthetic import make_feed


def test_plan_covers_network(tmp_path: Path):
    feed = load_feed(make_feed(tmp_path / "feed.zip"))
    cfg = Config()
    net = build_network(feed, cfg)

    hubs = pick_hubs(net, cfg)
    assert 3 <= len(hubs) <= cfg.n_hubs

    trunks, _ = build_trunks(net, hubs, cfg)
    assert trunks, "expected at least one trunk line"
    assert all(t.run_min <= cfg.max_trunk_min + 1 for t in trunks)
    hubs_on_trunks = {h for t in trunks for h in t.hubs}
    assert hubs_on_trunks == set(hubs)

    feeders, _ = build_feeders(net, hubs, trunks, cfg, route_patterns(feed, net))
    assert feeders, "expected feeders for stops away from the trunks"
    trunk_stops = {s for t in trunks for s in t.stops}
    assert all(len(f.stops) >= 2 and set(f.stops) <= set(f.path) for f in feeders)
    # Most feeders should connect to a trunk line.
    assert sum(bool(set(f.hubs) & trunk_stops) for f in feeders) >= 0.8 * len(feeders)

    from metrobus_efficiency.plan import _within_walk

    served = served_by_trunks(net, trunks, cfg) | _within_walk(net, [s for f in feeders for s in f.stops], cfg.trunk_catchment_m)
    active = set(net.nodes.index[net.nodes["departures"] > 0])
    assert len(active - served) <= 0.02 * len(active)


def test_cli_writes_outputs(tmp_path: Path, monkeypatch):
    gtfs = make_feed(tmp_path / "feed.zip")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    main(["--gtfs", str(gtfs)])
    for name in ("map.html", "plan.png", "summary.md", "lines.csv", "stops_plan.csv", "network.geojson", "metrics.json"):
        assert (tmp_path / "out" / name).exists(), name


def test_web_export(tmp_path: Path):
    from metrobus_efficiency.web_export import build_web_data

    feed = load_feed(make_feed(tmp_path / "feed.zip"))
    cfg = Config()
    net = build_network(feed, cfg)
    data = build_web_data(feed, net, cfg)
    ids = {p["id"] for p in data["places"]}
    assert data["scenarios"][0]["id"] == "today"
    assert len(data["scenarios"]) >= 2
    for s in data["scenarios"]:
        for line in s["lines"]:
            assert set(line["path"]) <= ids
            assert line["stop_idx"] == sorted(line["stop_idx"])
            assert all(0 <= i < len(line["path"]) for i in line["stop_idx"])
            assert line["cycle_min"] >= line["run_min"] > 0
            assert line["headway_min"] > 0
