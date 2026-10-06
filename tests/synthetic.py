"""Build a small fake GTFS feed shaped like a mid-size city, for tests and offline demos."""

from __future__ import annotations

import io
import math
import random
import zipfile
from pathlib import Path

LAT0, LON0 = 47.53, -52.82  # St. John's area
STEP_M = 300.0
GRID = 22


def _ll(i: int, j: int, offset: float = 0.0) -> tuple[float, float]:
    lat = LAT0 + (i * STEP_M + offset) / 111_320
    lon = LON0 + (j * STEP_M + offset) / (111_320 * math.cos(math.radians(LAT0)))
    return lat, lon


def _manhattan(a, b, rng):
    (i, j), (ti, tj) = a, b
    path = [(i, j)]
    while (i, j) != (ti, tj):
        moves = []
        if i != ti:
            moves.append((i + (1 if ti > i else -1), j))
        if j != tj:
            moves.append((i, j + (1 if tj > j else -1)))
        i, j = rng.choice(moves)
        path.append((i, j))
    return path


def make_feed(path: Path, seed: int = 7) -> Path:
    rng = random.Random(seed)
    anchors = {
        "Avalon Mall": (10, 9),
        "MUN Centre": (14, 11),
        "Downtown": (6, 18),
        "Village Mall": (4, 6),
        "Kelsey Dr": (17, 4),
        "Mount Pearl": (2, 1),
        "Torbay Rd": (19, 15),
        "Health Sciences": (15, 8),
    }
    names = list(anchors)
    route_plans = [
        ["Downtown", "MUN Centre", "Avalon Mall", "Village Mall"],
        ["Downtown", "Avalon Mall", "Mount Pearl"],
        ["Torbay Rd", "MUN Centre", "Health Sciences", "Kelsey Dr"],
        ["Village Mall", "Avalon Mall", "Health Sciences"],
        ["Mount Pearl", "Village Mall", "Downtown"],
        ["Kelsey Dr", "Avalon Mall", "Downtown"],
        ["Torbay Rd", "Downtown"],
        ["MUN Centre", "Kelsey Dr"],
    ]
    # Neighbourhood routes wandering off the main corners.
    for _ in range(6):
        a = rng.choice(names)
        far = (rng.randrange(GRID), rng.randrange(GRID))
        route_plans.append([a, far])

    stops: dict[tuple[int, int, int], str] = {}  # (i, j, direction) -> stop_id
    stop_rows, route_rows, trip_rows, st_rows = [], [], [], []

    def stop_id(cell, d):
        key = (cell[0], cell[1], d)
        if key not in stops:
            sid = f"S{len(stops) + 1}"
            stops[key] = sid
            lat, lon = _ll(cell[0], cell[1], 18.0 if d else 0.0)
            label = next((n for n, c in anchors.items() if c == cell), f"Street {cell[0]}-{cell[1]}")
            stop_rows.append(f"{sid},{label},{lat:.6f},{lon:.6f},0")
        return stops[key]

    for r, plan in enumerate(route_plans, start=1):
        pts = [anchors[p] if isinstance(p, str) else p for p in plan]
        cells = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            cells += _manhattan(a, b, rng)[1:]
        rid = f"R{r}"
        route_rows.append(f"{rid},{r},Route {r},3")
        headway = 15 if r <= 3 else (30 if r <= 8 else 60)
        for d, seq in ((0, cells), (1, list(reversed(cells)))):
            sids = [stop_id(c, d) for c in seq]
            for k, t0 in enumerate(range(6 * 3600, 23 * 3600, headway * 60)):
                tid = f"{rid}_{d}_{k}"
                trip_rows.append(f"{rid},WKDY,{tid},{d}")
                t = t0
                for n, sid in enumerate(sids, start=1):
                    hh = f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"
                    st_rows.append(f"{tid},{hh},{hh},{sid},{n}")
                    t += 55 + rng.randint(0, 20)

    files = {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nMB,Fake Metrobus,https://example.com,America/St_Johns\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon,location_type\n" + "\n".join(stop_rows) + "\n",
        "routes.txt": "route_id,route_short_name,route_long_name,route_type\n" + "\n".join(route_rows) + "\n",
        "trips.txt": "route_id,service_id,trip_id,direction_id\n" + "\n".join(trip_rows) + "\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n" + "\n".join(st_rows) + "\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        "WKDY,1,1,1,1,1,0,0,20260901,20261231\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    return path


if __name__ == "__main__":
    print(make_feed(Path("data/synthetic_gtfs.zip")))
