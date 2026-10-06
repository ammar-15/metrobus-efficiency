"""Settings, read from .env (or real environment variables) with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def _f(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _i(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _s(name: str, default: str) -> str:
    raw = os.getenv(name)
    return raw if raw not in (None, "") else default


@dataclass
class Config:
    # --- data -------------------------------------------------------------
    # Official Metrobus feed, plus MobilityDatabase mirrors (comma-separated) as fallbacks.
    gtfs_url: str = "http://www.metrobustransit.ca/google/google_transit.zip"
    gtfs_fallback_url: str = (
        "https://files.mobilitydatabase.org/mdb-758/latest.zip,"
        "https://files.mobilitydatabase.org/mdb-758/mdb-758-202609020057/mdb-758-202609020057.zip"
    )
    gtfs_path: str = ""  # local zip; skips downloading when set
    data_dir: Path = ROOT / "data"
    output_dir: Path = ROOT / "output"

    # --- maps ---------------------------------------------------------------
    # Optional. With a key, trunk and loop lines are drawn along real streets
    # (OpenRouteService). Without one, lines connect stops directly.
    ors_api_key: str = ""

    # --- network building -----------------------------------------------------
    merge_radius_m: float = 60.0  # stops this close (e.g. across the street) become one node
    hub_merge_radius_m: float = 250.0  # bays/stops this close count as one hub
    walk_speed_kmh: float = 4.8
    fallback_bus_speed_kmh: float = 22.0  # used when no scheduled link exists

    # --- hubs -----------------------------------------------------------------
    n_hubs: int = 10
    hub_min_spacing_m: float = 1200.0
    hub_min_share: float = 0.12  # a hub must be at least this busy relative to the busiest one

    # --- trunk lines ----------------------------------------------------------
    trunk_headway_min: float = 10.0
    max_trunk_min: float = 45.0  # longer lines are split at a middle hub
    min_trunk_min: float = 12.0  # shorter lines are joined onto a neighbouring line when possible
    trunk_stop_spacing_m: float = 400.0  # consolidated stop spacing on trunks
    trunk_shortcut_ratio: float = 1.6  # add a hub-to-hub link if the tree detour is this much longer
    trunk_catchment_m: float = 400.0  # stops within this walk of a trunk stop count as served
    dwell_saving_s: float = 12.0  # average time saved per stop removed from a trunk (decel, dwell, merge)

    # --- feeder loops ---------------------------------------------------------
    feeder_headway_min: float = 20.0
    max_loop_min: float = 30.0  # max round-trip running time of one loop
    min_loop_stops: int = 3

    # --- service assumptions ----------------------------------------------------
    service_hours_per_weekday: float = 18.0  # e.g. 6:30 to 00:30
    layover_factor: float = 1.10  # recovery time added to each cycle

    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, env_file: str | os.PathLike | None = None) -> "Config":
        load_dotenv(env_file or ROOT / ".env", override=False)
        c = cls()
        c.gtfs_url = _s("GTFS_URL", c.gtfs_url)
        c.gtfs_fallback_url = _s("GTFS_FALLBACK_URL", c.gtfs_fallback_url)
        c.gtfs_path = _s("GTFS_PATH", c.gtfs_path)
        c.data_dir = Path(_s("DATA_DIR", str(c.data_dir)))
        c.output_dir = Path(_s("OUTPUT_DIR", str(c.output_dir)))
        c.ors_api_key = _s("ORS_API_KEY", c.ors_api_key)
        c.merge_radius_m = _f("MERGE_RADIUS_M", c.merge_radius_m)
        c.hub_merge_radius_m = _f("HUB_MERGE_RADIUS_M", c.hub_merge_radius_m)
        c.walk_speed_kmh = _f("WALK_SPEED_KMH", c.walk_speed_kmh)
        c.fallback_bus_speed_kmh = _f("FALLBACK_BUS_SPEED_KMH", c.fallback_bus_speed_kmh)
        c.n_hubs = _i("N_HUBS", c.n_hubs)
        c.hub_min_spacing_m = _f("HUB_MIN_SPACING_M", c.hub_min_spacing_m)
        c.hub_min_share = _f("HUB_MIN_SHARE", c.hub_min_share)
        c.trunk_headway_min = _f("TRUNK_HEADWAY_MIN", c.trunk_headway_min)
        c.max_trunk_min = _f("MAX_TRUNK_MIN", c.max_trunk_min)
        c.min_trunk_min = _f("MIN_TRUNK_MIN", c.min_trunk_min)
        c.trunk_stop_spacing_m = _f("TRUNK_STOP_SPACING_M", c.trunk_stop_spacing_m)
        c.trunk_shortcut_ratio = _f("TRUNK_SHORTCUT_RATIO", c.trunk_shortcut_ratio)
        c.trunk_catchment_m = _f("TRUNK_CATCHMENT_M", c.trunk_catchment_m)
        c.dwell_saving_s = _f("DWELL_SAVING_S", c.dwell_saving_s)
        c.feeder_headway_min = _f("FEEDER_HEADWAY_MIN", c.feeder_headway_min)
        c.max_loop_min = _f("MAX_LOOP_MIN", c.max_loop_min)
        c.min_loop_stops = _i("MIN_LOOP_STOPS", c.min_loop_stops)
        c.service_hours_per_weekday = _f("SERVICE_HOURS_PER_WEEKDAY", c.service_hours_per_weekday)
        c.layover_factor = _f("LAYOVER_FACTOR", c.layover_factor)
        return c
