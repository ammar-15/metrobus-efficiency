"""Interactive map of the current network and the proposed trunk + feeder plan."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import folium
import requests

from .config import Config
from .network import Network
from .plan import Line

TRUNK_COLORS = ["#d62728", "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f"]
FEEDER_COLORS = ["#6baed6", "#74c476", "#fd8d3c", "#9e9ac8", "#fdae6b", "#a1d99b", "#fc9272", "#c6dbef"]


class Router:
    """Snaps a line to real streets with OpenRouteService if ORS_API_KEY is set; caches results."""

    URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"

    def __init__(self, cfg: Config):
        self.key = cfg.ors_api_key
        self.cache_path = cfg.data_dir / "ors_cache.json"
        self.cache: dict = {}
        if self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text())
            except json.JSONDecodeError:
                self.cache = {}
        self.warned = False

    def save(self) -> None:
        if self.cache:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache))

    def route(self, latlons: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if not self.key or len(latlons) < 2:
            return latlons
        out: list[tuple[float, float]] = []
        step = 49  # ORS allows 50 waypoints per request
        for i in range(0, len(latlons) - 1, step):
            chunk = latlons[i : i + step + 1]
            key = hashlib.sha1(json.dumps(chunk).encode()).hexdigest()
            if key not in self.cache:
                try:
                    r = requests.post(
                        self.URL,
                        headers={"Authorization": self.key, "Content-Type": "application/json"},
                        json={"coordinates": [[lon, lat] for lat, lon in chunk]},
                        timeout=30,
                    )
                    r.raise_for_status()
                    coords = r.json()["features"][0]["geometry"]["coordinates"]
                    self.cache[key] = [[lat, lon] for lon, lat in coords]
                except Exception as e:  # noqa: BLE001 - fall back to straight lines
                    if not self.warned:
                        print(f"OpenRouteService routing failed ({e}); drawing straight lines instead.")
                        self.warned = True
                    return latlons
            seg = [tuple(p) for p in self.cache[key]]
            out += seg if not out else seg[1:]
        return out


def _coords(net: Network, nodes: list[int]) -> list[tuple[float, float]]:
    return [(float(net.nodes.at[n, "lat"]), float(net.nodes.at[n, "lon"])) for n in nodes]


def _stop_waypoints(net: Network, ln: Line) -> list[int]:
    """Thin a line's driven path to fewer waypoints for routing, keeping its stops."""
    keep = set(ln.stops)
    return [n for i, n in enumerate(ln.path) if n in keep or i % 4 == 0 or i == len(ln.path) - 1]


def build_map(net: Network, hubs: list[int], trunks: list[Line], feeders: list[Line], cfg: Config, out: Path) -> Path:
    center = [float(net.nodes["lat"].mean()), float(net.nodes["lon"].mean())]
    m = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap", control_scale=True)
    router = Router(cfg)

    # Today's network, drawn thin and grey, thicker where more buses run.
    cur = folium.FeatureGroup(name="Today's bus network", show=True)
    max_trips = max((d.get("trips", 0) for *_, d in net.graph.edges(data=True)), default=1) or 1
    for u, v, d in net.graph.edges(data=True):
        if d.get("synthetic"):
            continue
        w = 1 + 4 * d.get("trips", 0) / max_trips
        folium.PolyLine(_coords(net, [u, v]), color="#9aa0a6", weight=w, opacity=0.6).add_to(cur)
    cur.add_to(m)

    tr = folium.FeatureGroup(name="Proposed trunk lines", show=True)
    for i, t in enumerate(trunks):
        color = TRUNK_COLORS[i % len(TRUNK_COLORS)]
        geom = router.route(_coords(net, _stop_waypoints(net, t)))
        tip = f"{t.name}: every {t.headway_min:g} min · {t.run_min:.0f} min one-way · {t.buses(cfg)} buses"
        folium.PolyLine(geom, color=color, weight=7, opacity=0.9, tooltip=tip).add_to(tr)
        for s in t.stops:
            folium.CircleMarker(
                _coords(net, [s])[0], radius=4, color=color, fill=True, fill_color="white", fill_opacity=1,
                tooltip=f"{t.name} stop: {net.nodes.at[s, 'name']}",
            ).add_to(tr)
    tr.add_to(m)

    fd = folium.FeatureGroup(name="Proposed feeder loops", show=True)
    for i, f in enumerate(feeders):
        color = FEEDER_COLORS[i % len(FEEDER_COLORS)]
        geom = router.route(_coords(net, _stop_waypoints(net, f)))
        tip = (
            f"{f.name} (from {net.nodes.at[f.hub, 'name']}): every {f.headway_min:g} min · "
            f"{f.run_min:.0f} min loop · {f.buses(cfg)} bus(es)"
        )
        if f.flags:
            tip += " · ⚠ " + "; ".join(f.flags)
        folium.PolyLine(geom, color=color, weight=4, opacity=0.85, dash_array="8 6", tooltip=tip).add_to(fd)
        for s in f.stops[1:]:
            folium.CircleMarker(
                _coords(net, [s])[0], radius=3, color=color, fill=True, fill_opacity=0.9,
                tooltip=f"{f.name} stop: {net.nodes.at[s, 'name']}",
            ).add_to(fd)
    fd.add_to(m)

    hb = folium.FeatureGroup(name="Hubs", show=True)
    for h in hubs:
        row = net.nodes.loc[h]
        folium.Marker(
            [row.lat, row.lon],
            tooltip=f"HUB: {row['name']}",
            popup=folium.Popup(
                f"<b>{row['name']}</b><br>{row['departures']} buses/weekday today<br>"
                f"Routes today: {', '.join(row['routes'])}",
                max_width=260,
            ),
            icon=folium.Icon(color="black", icon="star"),
        ).add_to(hb)
    hb.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    router.save()
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    return out
