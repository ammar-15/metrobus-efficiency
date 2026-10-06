"""Hub selection, trunk lines between hubs, and feeder loops around each hub."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from .config import Config
from .network import Network, haversine


# --------------------------------------------------------------------------- #
# Hubs
# --------------------------------------------------------------------------- #

def stop_scores(net: Network) -> np.ndarray:
    """How important each node is today: buses through it, boosted by route variety (transfers)."""
    n = net.nodes
    return n["departures"].to_numpy() * (1 + 0.5 * np.maximum(n["n_routes"].to_numpy() - 1, 0))


def pick_hubs(net: Network, cfg: Config) -> list[int]:
    """Greedy: busiest *areas* first (so a mall with 6 bays counts as one big hub), with min spacing."""
    nodes = net.nodes
    lat, lon = nodes["lat"].to_numpy(), nodes["lon"].to_numpy()
    score = stop_scores(net)
    d = haversine(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    area = (d <= cfg.hub_merge_radius_m).astype(float) @ score

    ids = nodes.index.to_numpy()
    hubs: list[int] = []
    floor = cfg.hub_min_share * area.max()
    for k in np.argsort(-area):
        if len(hubs) >= cfg.n_hubs or area[k] <= 0 or area[k] < floor:
            break
        if all(d[k, nodes.index.get_loc(h)] >= cfg.hub_min_spacing_m for h in hubs):
            hubs.append(int(ids[k]))
    return hubs


# --------------------------------------------------------------------------- #
# Trunk lines
# --------------------------------------------------------------------------- #

@dataclass
class Line:
    name: str
    kind: str  # "trunk" or "feeder"
    path: list[int]  # every node the bus drives through, in order
    stops: list[int]  # nodes where it stops
    run_min: float  # one-way (trunk) or full-loop (feeder) running time, minutes
    headway_min: float
    hub: int | None = None  # feeder's anchor hub
    hubs: list[int] = field(default_factory=list)  # trunk hubs, in order
    flags: list[str] = field(default_factory=list)

    @property
    def cycle_min(self) -> float:
        return self.run_min * (2 if self.kind == "trunk" else 1)

    def buses(self, cfg: Config) -> int:
        return max(1, math.ceil(self.cycle_min * cfg.layover_factor / self.headway_min))


def _passes_other_hub(net: Network, path: list[int], ends: tuple[int, int], hubs: list[int], radius: float) -> bool:
    others = [h for h in hubs if h not in ends]
    if not others:
        return False
    hl = net.nodes.loc[others, "lat"].to_numpy()
    hn = net.nodes.loc[others, "lon"].to_numpy()
    for p in path[1:-1]:
        if (haversine(net.nodes.at[p, "lat"], net.nodes.at[p, "lon"], hl, hn) <= radius).any():
            return True
    return False


def hub_graph(net: Network, hubs: list[int], cfg: Config) -> nx.Graph:
    """Spanning tree over hubs (direct hub-to-hub links only), plus shortcuts where the tree detours badly."""
    paths: dict[tuple[int, int], list[int]] = {}
    times: dict[tuple[int, int], float] = {}
    for h in hubs:
        dist, pth = nx.single_source_dijkstra(net.graph, h, weight="time")
        for k in hubs:
            if k != h and k in dist:
                paths[(h, k)] = pth[k]
                times[(h, k)] = dist[k]

    full = nx.Graph()
    full.add_nodes_from(hubs)
    direct = nx.Graph()
    direct.add_nodes_from(hubs)
    for (a, b), t in times.items():
        if a < b:
            full.add_edge(a, b, time=t, path=paths[(a, b)])
            if not _passes_other_hub(net, paths[(a, b)], (a, b), hubs, cfg.hub_merge_radius_m):
                direct.add_edge(a, b, time=t, path=paths[(a, b)])

    base = direct if nx.is_connected(direct) else full
    tree = nx.minimum_spanning_tree(base, weight="time")

    # Shortcuts: where going through the tree is much slower than the direct street path.
    candidates = []
    for a, b, data in direct.edges(data=True):
        if tree.has_edge(a, b):
            continue
        via_tree = nx.shortest_path_length(tree, a, b, weight="time")
        ratio = via_tree / max(data["time"], 1)
        if ratio >= cfg.trunk_shortcut_ratio:
            candidates.append((ratio, a, b, data))
    for ratio, a, b, data in sorted(candidates, reverse=True)[: max(1, len(hubs) // 3)]:
        # Re-check against the growing network so shortcuts don't duplicate each other.
        if nx.shortest_path_length(tree, a, b, weight="time") / max(data["time"], 1) >= cfg.trunk_shortcut_ratio:
            tree.add_edge(a, b, **data)
    return tree


def _longest_unused_path(g: nx.Graph, used: set[frozenset]) -> list[int]:
    """Longest simple path (by time) that only uses edges not yet assigned to a line."""
    best: tuple[float, list[int]] = (0.0, [])

    def dfs(node: int, path: list[int], seen_edges: set, t: float):
        nonlocal best
        if t > best[0]:
            best = (t, list(path))
        for nb in g.neighbors(node):
            e = frozenset((node, nb))
            if e in used or e in seen_edges or nb in path:
                continue
            seen_edges.add(e)
            path.append(nb)
            dfs(nb, path, seen_edges, t + g[node][nb]["time"])
            path.pop()
            seen_edges.discard(e)

    for start in g.nodes:
        dfs(start, [start], set(), 0.0)
    return best[1]


def consolidate_stops(net: Network, path: list[int], keep: set[int], spacing: float) -> list[int]:
    """Pick trunk stops roughly every `spacing` metres, always keeping hubs, preferring busy stops."""
    score = dict(zip(net.nodes.index, stop_scores(net)))
    cum = [0.0]
    for u, v in zip(path, path[1:]):
        cum.append(cum[-1] + net.dist_m(u, v))
    kept = [0]
    i = 1
    while i < len(path):
        if path[i] in keep:
            kept.append(i)
            i += 1
            continue
        since = cum[i] - cum[kept[-1]]
        if since < 0.75 * spacing:
            i += 1
            continue
        # Window of candidates: up to 1.5x spacing ahead, stopping at the next hub.
        window = [i]
        j = i + 1
        while j < len(path) and cum[j] - cum[kept[-1]] <= 1.5 * spacing and path[j] not in keep:
            window.append(j)
            j += 1
        pick = max(window, key=lambda k: score.get(path[k], 0))
        kept.append(pick)
        i = pick + 1
    if kept[-1] != len(path) - 1:
        kept.append(len(path) - 1)
    out: list[int] = []
    for k in kept:
        if not out or out[-1] != path[k]:
            out.append(path[k])
    return out


def _seq_time(hg: nx.Graph, seq: list[int]) -> float:
    return sum(hg[a][b]["time"] for a, b in zip(seq, seq[1:]))


def _split_long(hg: nx.Graph, seq: list[int], max_s: float) -> list[list[int]]:
    """Split a hub sequence at the hub nearest its midpoint until every piece fits max_s."""
    total = _seq_time(hg, seq)
    if total <= max_s or len(seq) < 3:
        return [seq]
    cum = [0.0]
    for a, b in zip(seq, seq[1:]):
        cum.append(cum[-1] + hg[a][b]["time"])
    k = min(range(1, len(seq) - 1), key=lambda i: abs(cum[i] - total / 2))
    return _split_long(hg, seq[: k + 1], max_s) + _split_long(hg, seq[k:], max_s)


def _join_short(hg: nx.Graph, seqs: list[list[int]], min_s: float, max_s: float) -> list[list[int]]:
    """Attach very short lines onto a neighbouring line that ends at the same hub."""
    seqs = [list(s) for s in seqs]
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(seqs):
            if _seq_time(hg, s) >= min_s:
                continue
            best = None
            for j, o in enumerate(seqs):
                if i == j:
                    continue
                for a in (s, s[::-1]):
                    for b in (o, o[::-1]):
                        if a[-1] == b[0] and not (set(a[:-1]) & set(b)):
                            joined = a + b[1:]
                            t = _seq_time(hg, joined)
                            if t <= max_s and (best is None or t < best[0]):
                                best = (t, j, joined)
            if best:
                _, j, joined = best
                seqs = [x for k, x in enumerate(seqs) if k not in (i, j)] + [joined]
                changed = True
                break
    return seqs


def build_trunks(net: Network, hubs: list[int], cfg: Config) -> tuple[list[Line], nx.Graph]:
    hg = hub_graph(net, hubs, cfg)
    used: set[frozenset] = set()
    seqs: list[list[int]] = []
    while len(used) < hg.number_of_edges():
        hub_seq = _longest_unused_path(hg, used)
        if len(hub_seq) < 2:
            break
        for a, b in zip(hub_seq, hub_seq[1:]):
            used.add(frozenset((a, b)))
        seqs += _split_long(hg, hub_seq, cfg.max_trunk_min * 60)
    seqs = _join_short(hg, seqs, cfg.min_trunk_min * 60, cfg.max_trunk_min * 60)
    seqs.sort(key=lambda q: -_seq_time(hg, q))

    lines: list[Line] = []
    for hub_seq in seqs:
        path: list[int] = [hub_seq[0]]
        for a, b in zip(hub_seq, hub_seq[1:]):
            seg = hg[a][b]["path"]
            seg = seg if seg[0] == a else list(reversed(seg))
            path += seg[1:]
        stops = consolidate_stops(net, path, set(hubs), cfg.trunk_stop_spacing_m)
        removed = len(set(path)) - len(set(stops))
        run_s = net.path_time(path) - removed * cfg.dwell_saving_s
        flags = []
        if run_s < cfg.min_trunk_min * 60:
            flags.append("short: could run as an extension of a feeder loop instead")
        lines.append(
            Line(
                name=f"T{len(lines) + 1}",
                kind="trunk",
                path=path,
                stops=stops,
                run_min=max(run_s, 60) / 60,
                headway_min=cfg.trunk_headway_min,
                hubs=hub_seq,
                flags=flags,
            )
        )
    return lines, hg


# --------------------------------------------------------------------------- #
# Feeder loops
# --------------------------------------------------------------------------- #

class _TimeCache:
    def __init__(self, net: Network):
        self.net = net
        self._cache: dict[int, dict[int, float]] = {}

    def __call__(self, a: int, b: int) -> float:
        if a == b:
            return 0.0
        if a not in self._cache:
            self._cache[a] = nx.single_source_dijkstra_path_length(self.net.graph, a, weight="time")
        return self._cache[a].get(b, self.net.straight_time(a, b))


def _loop_order(hub: int, members: list[int], tt: _TimeCache, two_opt: bool = True) -> tuple[list[int], float]:
    """Nearest-neighbour tour from the hub through all members and back, then 2-opt."""
    tour = [hub]
    left = set(members)
    while left:
        nxt = min(left, key=lambda m: tt(tour[-1], m))
        tour.append(nxt)
        left.remove(nxt)
    tour.append(hub)

    def cost(t):
        return sum(tt(u, v) for u, v in zip(t, t[1:]))

    best = cost(tour)
    improved = two_opt
    while improved and len(tour) > 4:
        improved = False
        for i in range(1, len(tour) - 2):
            for k in range(i + 1, len(tour) - 1):
                cand = tour[:i] + tour[i : k + 1][::-1] + tour[k + 1 :]
                c = cost(cand)
                if c + 1e-6 < best:
                    tour, best, improved = cand, c, True
    return tour, best


def _bearing(net: Network, hub: int, n: int) -> float:
    h, p = net.nodes.loc[hub], net.nodes.loc[n]
    return math.atan2(p.lat - h.lat, (p.lon - h.lon) * math.cos(math.radians(h.lat)))


def served_by_trunks(net: Network, trunks: list[Line], cfg: Config) -> set[int]:
    stop_nodes = sorted({s for t in trunks for s in t.stops})
    if not stop_nodes:
        return set()
    sl = net.nodes.loc[stop_nodes, "lat"].to_numpy()
    sn = net.nodes.loc[stop_nodes, "lon"].to_numpy()
    out = set()
    for n, row in net.nodes.iterrows():
        if (haversine(row.lat, row.lon, sl, sn) <= cfg.trunk_catchment_m).any():
            out.add(int(n))
    return out


def build_feeders(net: Network, hubs: list[int], trunks: list[Line], cfg: Config) -> tuple[list[Line], dict[int, int]]:
    covered = served_by_trunks(net, trunks, cfg)
    todo = [int(n) for n in net.nodes.index if n not in covered and net.nodes.at[n, "departures"] > 0]
    if not todo:
        return [], {}

    # Each uncovered stop goes to the hub it can reach fastest.
    dist, paths = nx.multi_source_dijkstra(net.graph, set(hubs), weight="time")
    assign: dict[int, list[int]] = {h: [] for h in hubs}
    for n in todo:
        if n in paths:
            assign[paths[n][0]].append(n)

    tt = _TimeCache(net)
    max_s = cfg.max_loop_min * 60
    feeders: list[Line] = []
    owner: dict[int, int] = {}

    for hub in hubs:
        members = assign[hub]
        if not members:
            continue
        # Sweep around the hub, starting at the widest empty gap so no loop straddles it.
        ang = sorted(members, key=lambda m: _bearing(net, hub, m))
        b = [_bearing(net, hub, m) for m in ang]
        gaps = [(b[(i + 1) % len(b)] - b[i]) % (2 * math.pi) for i in range(len(b))]
        start = (int(np.argmax(gaps)) + 1) % len(ang)
        ang = ang[start:] + ang[:start]

        groups: list[list[int]] = []
        cur: list[int] = []
        for m in ang:
            trial = cur + [m]
            _, t = _loop_order(hub, trial, tt, two_opt=False)
            if cur and t > max_s:
                groups.append(cur)
                cur = [m]
            else:
                cur = trial
        if cur:
            groups.append(cur)

        # Fold tiny groups into a neighbour when it still fits the time limit.
        merged: list[list[int]] = []
        for g in groups:
            if merged and len(g) < cfg.min_loop_stops:
                _, t = _loop_order(hub, merged[-1] + g, tt)
                if t <= max_s * 1.15:
                    merged[-1] += g
                    continue
            merged.append(g)
        if len(merged) > 1 and len(merged[0]) < cfg.min_loop_stops:
            _, t = _loop_order(hub, merged[1] + merged[0], tt)
            if t <= max_s * 1.15:
                merged[1] += merged.pop(0)

        for g in merged:
            tour, t = _loop_order(hub, g, tt)
            path = [tour[0]]
            for u, v in zip(tour, tour[1:]):
                try:
                    seg = net.path(u, v)
                except nx.NetworkXNoPath:
                    seg = [u, v]
                path += seg[1:]
            flags = []
            if t > max_s * 1.15:
                flags.append("long: these stops are far from any hub; consider on-demand service")
            if len(g) < cfg.min_loop_stops:
                flags.append("few stops: candidate for on-demand or merging into a trunk")
            line = Line(
                name=f"F{len(feeders) + 1}",
                kind="feeder",
                path=path,
                stops=tour[:-1],
                run_min=max(t, 60) / 60,
                headway_min=cfg.feeder_headway_min,
                hub=hub,
                flags=flags,
            )
            line.hubs = [hub]
            feeders.append(line)
            for m in g:
                owner[m] = len(feeders) - 1
    return feeders, owner
