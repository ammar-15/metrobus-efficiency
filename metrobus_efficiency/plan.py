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
            # Name the hub after its busiest stop (e.g. the mall terminal, not a stop at its edge).
            area_idx = np.where(d[k] <= cfg.hub_merge_radius_m)[0]
            best = int(area_idx[np.argmax(score[area_idx])])
            hubs.append(int(ids[best]))
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
    hubs: list[int] = field(default_factory=list)  # trunk hubs in order, or a feeder's trunk ends
    flags: list[str] = field(default_factory=list)
    two_way: bool | None = None  # feeders: True for out-and-back or end-to-end, False for a loop
    source: str | None = None  # feeders: today's route it follows

    @property
    def cycle_min(self) -> float:
        both = self.kind == "trunk" or bool(self.two_way)
        return self.run_min * (2 if both else 1)

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
# Feeders
# --------------------------------------------------------------------------- #
#
# Feeders reuse today's routes where they serve neighbourhoods away from the
# trunks: each route is cut where it reaches trunk territory, and the uncovered
# part becomes a feeder that ends at the nearest trunk stop. Streets, stops and
# running times all come from today's schedule.


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


def _within_walk(net: Network, nodes: list[int], radius: float) -> set[int]:
    if not nodes:
        return set()
    lat = net.nodes["lat"].to_numpy()
    lon = net.nodes["lon"].to_numpy()
    ids = net.nodes.index.to_numpy()
    out: set[int] = set()
    for n in set(nodes):
        d = haversine(net.nodes.at[n, "lat"], net.nodes.at[n, "lon"], lat, lon)
        out |= {int(x) for x in ids[d <= radius]}
    return out


def _runs(flags: list[bool], max_gap: int) -> list[tuple[int, int]]:
    """Index ranges where flags are True, joining runs separated by short gaps."""
    runs: list[list[int]] = []
    for i, f in enumerate(flags):
        if not f:
            continue
        if runs and i - runs[-1][1] - 1 <= max_gap:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return [(a, b) for a, b in runs]


def _segment_time(net: Network, path: list[int]) -> float:
    t = 0.0
    for u, v in zip(path, path[1:]):
        if net.graph.has_edge(u, v):
            t += net.graph[u][v]["time"]
        else:
            t += net.straight_time(u, v)
    return t


def build_feeders(
    net: Network, hubs: list[int], trunks: list[Line], cfg: Config, patterns: list[dict] | None = None
) -> tuple[list[Line], dict[int, int]]:
    if not patterns:
        return [], {}
    covered = served_by_trunks(net, trunks, cfg)
    trunk_stops = {s for t in trunks for s in t.stops}
    hub_set = set(hubs)
    active = {int(n) for n in net.nodes.index if net.nodes.at[n, "departures"] > 0}
    need = active - covered

    # Routes that reach the most stranded stops go first.
    def gain(p):
        return len(set(p["path"]) & need)

    feeders: list[Line] = []
    owner: dict[int, int] = {}
    for pat in sorted(patterns, key=gain, reverse=True):
        path = pat["path"]
        if not (set(path) & need):
            continue
        outside = [n not in covered for n in path]
        for a, b in _runs(outside, max_gap=3):
            if not (set(path[a : b + 1]) & need):
                continue
            # Extend along the route to the nearest trunk stop at each end, so riders can transfer.
            lo, hi = a, b
            for k in range(a - 1, max(a - 15, -1), -1):
                if path[k] in trunk_stops:
                    lo = k
                    break
            for k in range(b + 1, min(b + 15, len(path))):
                if path[k] in trunk_stops:
                    hi = k
                    break
            seg = path[lo : hi + 1]
            if len(seg) < 2:
                continue
            ends = [n for n in (seg[0], seg[-1]) if n in trunk_stops]
            # Stops: today's stops on the uncovered part, plus the trunk stop(s) it connects to.
            stops = [n for i, n in enumerate(seg) if (lo + i >= a and lo + i <= b and n in active) or n in ends]
            stops = list(dict.fromkeys(stops))
            if len(stops) < 2:
                continue
            is_loop = seg[0] == seg[-1]
            run_s = _segment_time(net, seg)
            anchor = next((n for n in ends if n in hub_set), ends[0] if ends else None)
            flags = []
            new_stops = set(stops) & need
            if len(new_stops) < cfg.min_loop_stops:
                flags.append("few stops: candidate for on-demand service")
            if not ends:
                flags.append("doesn't reach a trunk line: riders can't transfer")
            if run_s / 60 > cfg.max_loop_min * 1.5:
                flags.append("long: could be split or partly replaced by on-demand service")
            line = Line(
                name=f"F{len(feeders) + 1}",
                kind="feeder",
                path=seg,
                stops=stops,
                run_min=max(run_s, 60) / 60,
                headway_min=cfg.feeder_headway_min,
                hub=anchor,
                hubs=ends,
                flags=flags,
                two_way=not is_loop,
                source=pat.get("name"),
            )
            feeders.append(line)
            served = _within_walk(net, stops, cfg.trunk_catchment_m)
            for n in served & need:
                owner[n] = len(feeders) - 1
            need -= served
    return feeders, owner
