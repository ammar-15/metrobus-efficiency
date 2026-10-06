"""Download and load a GTFS feed, reduced to one representative weekday."""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

from .config import Config

HEADERS = {"User-Agent": "Mozilla/5.0 (metrobus-efficiency; transit planning research)"}


def download_feed(cfg: Config, force: bool = False) -> Path:
    """Return a path to the GTFS zip, downloading it into data/ if needed."""
    if cfg.gtfs_path:
        p = Path(cfg.gtfs_path)
        if not p.exists():
            raise FileNotFoundError(f"GTFS_PATH points to a missing file: {p}")
        return p

    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    target = cfg.data_dir / "metrobus_gtfs.zip"
    if target.exists() and not force:
        return target

    urls = [cfg.gtfs_url] + [u.strip() for u in cfg.gtfs_fallback_url.split(",") if u.strip()]
    errors = []
    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            zipfile.ZipFile(io.BytesIO(r.content)).testzip()  # make sure it's a real zip
            target.write_bytes(r.content)
            print(f"Downloaded GTFS from {url} ({len(r.content) / 1e6:.1f} MB)")
            return target
        except Exception as e:  # noqa: BLE001 - try the next mirror
            errors.append(f"  {url}: {e}")
    raise RuntimeError(
        "Could not download the Metrobus GTFS feed. Download it manually and set "
        "GTFS_PATH in .env.\n" + "\n".join(errors)
    )


def _read(z: zipfile.ZipFile, name: str, required: bool = True) -> pd.DataFrame | None:
    matches = [n for n in z.namelist() if n.split("/")[-1] == name]
    if not matches:
        if required:
            raise ValueError(f"GTFS feed is missing {name}")
        return None
    with z.open(matches[0]) as f:
        df = pd.read_csv(f, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    return df


def to_seconds(s: pd.Series) -> pd.Series:
    """'25:10:00' -> 90600. GTFS times can pass 24:00 for after-midnight trips."""
    parts = s.str.strip().str.split(":", expand=True)
    out = pd.to_numeric(parts[0], errors="coerce") * 3600
    out = out + pd.to_numeric(parts[1], errors="coerce") * 60
    out = out + pd.to_numeric(parts[2], errors="coerce")
    return out


@dataclass
class Feed:
    stops: pd.DataFrame  # stop_id, stop_name, lat, lon
    routes: pd.DataFrame
    trips: pd.DataFrame  # trips running on the chosen day
    stop_times: pd.DataFrame  # for those trips, with arr/dep in seconds
    service_date: dt.date


def _active_services(cal: pd.DataFrame | None, cal_dates: pd.DataFrame | None, day: dt.date) -> set[str]:
    active: set[str] = set()
    ymd = day.strftime("%Y%m%d")
    if cal is not None and len(cal):
        wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
        m = (cal["start_date"] <= ymd) & (cal["end_date"] >= ymd) & (cal[wd] == "1")
        active |= set(cal.loc[m, "service_id"])
    if cal_dates is not None and len(cal_dates):
        today = cal_dates[cal_dates["date"] == ymd]
        active |= set(today.loc[today["exception_type"] == "1", "service_id"])
        active -= set(today.loc[today["exception_type"] == "2", "service_id"])
    return active


def _pick_weekday(trips: pd.DataFrame, cal, cal_dates) -> tuple[dt.date, set[str]]:
    """Pick the weekday with the most scheduled trips (a normal school-season weekday)."""
    dates: list[str] = []
    if cal is not None and len(cal):
        dates += list(cal["start_date"]) + list(cal["end_date"])
    if cal_dates is not None and len(cal_dates):
        dates += list(cal_dates["date"])
    if not dates:
        raise ValueError("Feed has no calendar.txt or calendar_dates.txt")
    start = dt.datetime.strptime(min(dates), "%Y%m%d").date()
    end = dt.datetime.strptime(max(dates), "%Y%m%d").date()
    today = dt.date.today()
    if start <= today <= end:  # prefer upcoming service if the feed covers today
        start = today
    end = min(end, start + dt.timedelta(days=120))

    trips_per_service = trips.groupby("service_id").size()
    best: tuple[int, dt.date, set[str]] | None = None
    d = start
    while d <= end:
        if d.weekday() < 5:
            svc = _active_services(cal, cal_dates, d)
            n = int(trips_per_service.reindex(list(svc)).fillna(0).sum())
            if best is None or n > best[0]:
                best = (n, d, svc)
        d += dt.timedelta(days=1)
    if best is None or best[0] == 0:
        raise ValueError("Could not find a weekday with scheduled trips in this feed")
    return best[1], best[2]


def load_feed(path: Path) -> Feed:
    with zipfile.ZipFile(path) as z:
        stops = _read(z, "stops.txt")
        routes = _read(z, "routes.txt")
        trips = _read(z, "trips.txt")
        stop_times = _read(z, "stop_times.txt")
        cal = _read(z, "calendar.txt", required=False)
        cal_dates = _read(z, "calendar_dates.txt", required=False)

    day, services = _pick_weekday(trips, cal, cal_dates)
    trips = trips[trips["service_id"].isin(services)].copy()

    stop_times = stop_times[stop_times["trip_id"].isin(set(trips["trip_id"]))].copy()
    stop_times["arr"] = to_seconds(stop_times["arrival_time"].replace("", None).fillna(stop_times["departure_time"]))
    stop_times["dep"] = to_seconds(stop_times["departure_time"].replace("", None).fillna(stop_times["arrival_time"]))
    stop_times["stop_sequence"] = pd.to_numeric(stop_times["stop_sequence"])
    stop_times = stop_times.sort_values(["trip_id", "stop_sequence"])
    # Fill untimed intermediate stops by interpolation within each trip.
    for col in ("arr", "dep"):
        stop_times[col] = stop_times.groupby("trip_id")[col].transform(
            lambda s: s.interpolate(limit_direction="both")
        )

    stops = stops.copy()
    if "location_type" in stops.columns:
        stops = stops[stops["location_type"].isin(["", "0"])]
    stops["lat"] = pd.to_numeric(stops["stop_lat"])
    stops["lon"] = pd.to_numeric(stops["stop_lon"])
    if "stop_name" not in stops.columns:
        stops["stop_name"] = stops["stop_id"]
    used = set(stop_times["stop_id"])
    stops = stops[stops["stop_id"].isin(used)][["stop_id", "stop_name", "lat", "lon"]].reset_index(drop=True)

    routes = routes.copy()
    if "route_short_name" not in routes.columns:
        routes["route_short_name"] = ""
    long_name = routes["route_long_name"] if "route_long_name" in routes.columns else routes["route_id"]
    routes["route_short_name"] = routes["route_short_name"].where(routes["route_short_name"] != "", long_name)
    trips = trips.merge(routes[["route_id", "route_short_name"]], on="route_id", how="left")
    return Feed(stops=stops, routes=routes, trips=trips, stop_times=stop_times, service_date=day)
