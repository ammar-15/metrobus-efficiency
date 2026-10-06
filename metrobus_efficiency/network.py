"""Turn the GTFS schedule into a street-level travel-time graph of stop 'nodes'.

Paired stops on opposite sides of the street are merged into one node so the
planner can think in places rather than in directional stop poles.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd

from .config import Config
from .gtfs import Feed

EARTH_R = 6_371_000.0


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres. Works on scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def pairwise(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    return haversine(lat[:, None], lon[:, None], lat[None, :], lon[None, :])


def cluster_points(lat: np.ndarray, lon: np.ndarray, radius_m: float) -> np.ndarray:
    """Single-linkage clustering: points within radius_m end up in one group."""
    n = len(lat)
    parent = np.arange(n)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    d = pairwise(lat, lon)
    ii, jj = np.where(np.triu(d <= radius_m, k=1))
    for i, j in zip(ii, jj):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri
    roots = np.array([find(i) for i in range(n)])
    _, labels = np.unique(roots, return_inverse=True)
    return labels


@dataclass
class Network:
    nodes: pd.DataFrame  # node, lat, lon, name, stop_ids, departures, routes, n_routes
    stop_to_node: dict[str, int]
    graph: nx.Graph  # undirected, edge weight 'time' in seconds, 'trips' per day
    cfg: Config

    def straight_time(self, a: int, b: int) -> float:
        na, nb = self.nodes.loc[a], self.nodes.loc[b]
        d = haversine(na.lat, na.lon, nb.lat, nb.lon) * 1.3  # street detour factor
        return d / (self.cfg.fallback_bus_speed_kmh / 3.6)

    def dist_m(self, a: int, b: int) -> float:
        na, nb = self.nodes.loc[a], self.nodes.loc[b]
        return float(haversine(na.lat, na.lon, nb.lat, nb.lon))

    def path(self, a: int, b: int) -> list[int]:
        return nx.shortest_path(self.graph, a, b, weight="time")

    def path_time(self, path: list[int]) -> float:
        return float(sum(self.graph[u][v]["time"] for u, v in zip(path, path[1:])))


def build_network(feed: Feed, cfg: Config) -> Network:
    stops = feed.stops
    labels = cluster_points(stops["lat"].to_numpy(), stops["lon"].to_numpy(), cfg.merge_radius_m)
    stops = stops.assign(node=labels)
    stop_to_node = dict(zip(stops["stop_id"], stops["node"]))

    st = feed.stop_times.merge(feed.trips[["trip_id", "route_short_name"]], on="trip_id", how="left")
    st = st[st["stop_id"].isin(stop_to_node)].copy()
    st["node"] = st["stop_id"].map(stop_to_node)

    # Node attributes ---------------------------------------------------------
    deps = st.groupby("node").size()
    routes = st.groupby("node")["route_short_name"].agg(lambda s: sorted(set(map(str, s))))
    nodes = (
        stops.groupby("node")
        .agg(
            lat=("lat", "mean"),
            lon=("lon", "mean"),
            name=("stop_name", lambda s: s.value_counts().index[0]),
            stop_ids=("stop_id", list),
        )
        .reset_index()
    )
    nodes["departures"] = nodes["node"].map(deps).fillna(0).astype(int)
    nodes["routes"] = nodes["node"].map(routes).apply(lambda r: r if isinstance(r, list) else [])
    nodes["n_routes"] = nodes["routes"].apply(len)
    nodes = nodes.set_index("node", drop=False)

    # Edges from consecutive stops on every trip -------------------------------
    st = st.sort_values(["trip_id", "stop_sequence"])
    nxt = st.groupby("trip_id").shift(-1)
    seg = pd.DataFrame(
        {
            "u": st["node"],
            "v": nxt["node"],
            "t": nxt["arr"] - st["dep"],
        }
    ).dropna()
    seg = seg[seg["u"] != seg["v"]]
    seg["u"] = seg["u"].astype(int)
    seg["v"] = seg["v"].astype(int)
    seg["a"] = seg[["u", "v"]].min(axis=1)
    seg["b"] = seg[["u", "v"]].max(axis=1)
    agg = seg.groupby(["a", "b"]).agg(t=("t", "median"), trips=("t", "size")).reset_index()

    g = nx.Graph()
    for n, row in nodes.iterrows():
        g.add_node(int(n), lat=row.lat, lon=row.lon)
    for row in agg.itertuples():
        d = haversine(nodes.at[row.a, "lat"], nodes.at[row.a, "lon"], nodes.at[row.b, "lat"], nodes.at[row.b, "lon"])
        # Guard against zero/negative scheduled times (same-minute timepoints).
        min_t = d / (60 / 3.6)  # never faster than 60 km/h
        g.add_edge(int(row.a), int(row.b), time=float(max(row.t, min_t, 15.0)), trips=int(row.trips), length=float(d))

    net = Network(nodes=nodes, stop_to_node=stop_to_node, graph=g, cfg=cfg)
    _connect_components(net)
    return net


def _connect_components(net: Network) -> None:
    """Link any isolated pieces of the graph to the main piece with a straight-line hop."""
    comps = sorted(nx.connected_components(net.graph), key=len, reverse=True)
    if len(comps) <= 1:
        return
    main = list(comps[0])
    mlat = net.nodes.loc[main, "lat"].to_numpy()
    mlon = net.nodes.loc[main, "lon"].to_numpy()
    for comp in comps[1:]:
        best = None
        for n in comp:
            d = haversine(net.nodes.at[n, "lat"], net.nodes.at[n, "lon"], mlat, mlon)
            k = int(np.argmin(d))
            if best is None or d[k] < best[0]:
                best = (float(d[k]), n, main[k])
        _, a, b = best
        net.graph.add_edge(a, b, time=net.straight_time(a, b), trips=0, length=best[0], synthetic=True)
        main += list(comp)
        mlat = net.nodes.loc[main, "lat"].to_numpy()
        mlon = net.nodes.loc[main, "lon"].to_numpy()


def route_patterns(feed: Feed, net: Network, min_trips: int = 2) -> list[dict]:
    """Every distinct stop sequence today's routes run, as place ids (busiest first per route)."""
    st = feed.stop_times[["trip_id", "stop_id", "stop_sequence"]].merge(
        feed.trips[["trip_id", "route_id", "route_short_name"]], on="trip_id"
    )
    st["node"] = st["stop_id"].map(net.stop_to_node)
    st = st.dropna(subset=["node"]).sort_values(["trip_id", "stop_sequence"])
    seqs = st.groupby("trip_id").agg(route_id=("route_id", "first"), name=("route_short_name", "first"), nodes=("node", list))
    seqs["path"] = seqs["nodes"].apply(lambda ns: tuple(int(n) for i, n in enumerate(ns) if i == 0 or n != ns[i - 1]))
    out = []
    for (rid, name, path), g in seqs.groupby(["route_id", "name", "path"]):
        if len(g) >= min_trips and len(path) >= 2:
            out.append({"route_id": rid, "name": str(name), "path": list(path), "trips": int(len(g))})
    out.sort(key=lambda p: -p["trips"])
    return out
