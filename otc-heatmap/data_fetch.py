"""Fetch and process ICOS OTC data.

Level-2 stats are cached on disk (pickle) and only recomputed for stations
whose set of data-object URIs has changed since the last run.
NRT (Level-1) is always refreshed as it is a lightweight SPARQL query.
"""

import pickle
import time
import logging
import pandas as pd
import numpy as np
from icoscp_core.icos import data, meta, OCEAN_STATION
from icoscp_core.sparql import as_string, as_uri

from config import IGNORE_STATIONS, KPI_COL, NRT_QUERY, L2_LATEST_QUERY, CACHE_TTL, DISK_CACHE_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
_cache: dict = {}
_cache_ts: float = 0.0


def _is_stale() -> bool:
    return (time.time() - _cache_ts) > CACHE_TTL


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------
def _load_disk_cache() -> dict:
    """Load persisted L2 results from disk. Returns empty dict if not found."""
    try:
        with open(DISK_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("Could not load disk cache (%s) — starting fresh.", e)
        return {}


def _save_disk_cache(disk: dict) -> None:
    """Persist L2 results to disk."""
    try:
        with open(DISK_CACHE_PATH, "wb") as f:
            pickle.dump(disk, f)
    except Exception as e:
        logger.warning("Could not save disk cache: %s", e)


# ---------------------------------------------------------------------------
# NRT (Level 1)
# ---------------------------------------------------------------------------
def _fetch_nrt() -> pd.DataFrame:
    """Run the NRT SPARQL query and return a DataFrame with Station,
    DataStartTime, DataEndTime (datetime), and DataObject (URL)."""
    station_uri_to_id = {
        s.uri: s.id
        for s in meta.list_stations(OCEAN_STATION)
    }
    rows = [
        {
            "Station": station_uri_to_id.get(as_uri("station", r), as_uri("station", r)),
            "DataStartTime": as_string("timeStart", r),
            "DataEndTime": as_string("timeEnd", r),
            "DataObject": as_uri("dobj", r),
        }
        for r in meta.sparql_select(NRT_QUERY).bindings
    ]
    df = pd.DataFrame(rows)
    df["DataStartTime"] = pd.to_datetime(df["DataStartTime"])
    df["DataEndTime"] = pd.to_datetime(df["DataEndTime"])
    return df


def _build_nrt_lookups(nrt_df: pd.DataFrame) -> tuple[dict, dict, dict]:
    """Return (nrt_latest, nrt_urls, nrt_start) dicts keyed by station name."""
    info = (
        nrt_df
        .sort_values("DataEndTime", ascending=False)
        .drop_duplicates(subset="Station", keep="first")
        .set_index("Station")
    )
    nrt_latest = info["DataEndTime"].dt.strftime("%Y-%m-%d").to_dict()
    nrt_urls = info["DataObject"].to_dict()
    nrt_start = info["DataStartTime"].dt.tz_localize(None).dt.strftime("%Y-%m-%d").to_dict()
    return nrt_latest, nrt_urls, nrt_start


# ---------------------------------------------------------------------------
# Level 2 latest release (SPARQL)
# ---------------------------------------------------------------------------
def _fetch_l2_latest() -> pd.DataFrame:
    """Run the L2-latest SPARQL query and return a DataFrame with Station,
    DataEndTime (datetime), and DataObject (URL)."""
    station_uri_to_id = {
        s.uri: s.id
        for s in meta.list_stations(OCEAN_STATION)
    }
    rows = [
        {
            "Station": station_uri_to_id.get(as_uri("station", r), as_uri("station", r)),
            "DataEndTime": as_string("timeEnd", r),
            "DataObject": as_uri("dobj", r),
        }
        for r in meta.sparql_select(L2_LATEST_QUERY).bindings
    ]
    df = pd.DataFrame(rows)
    df["DataEndTime"] = pd.to_datetime(df["DataEndTime"])
    return df


def _build_l2_latest_lookups(df: pd.DataFrame) -> tuple[dict, dict]:
    """Return (l2_latest, l2_urls) dicts keyed by station name."""
    info = (
        df
        .sort_values("DataEndTime", ascending=False)
        .drop_duplicates(subset="Station", keep="first")
        .set_index("Station")
    )
    l2_latest = info["DataEndTime"].dt.tz_localize(None).dt.strftime("%Y-%m-%d").to_dict()
    l2_urls = info["DataObject"].to_dict()
    return l2_latest, l2_urls


# ---------------------------------------------------------------------------
# Level 2 KPI (incremental, disk-cached)
# ---------------------------------------------------------------------------
def _process_station(station_id: str, station_dobjs: list) -> pd.DataFrame | None:
    """Download and compute monthly KPI for one station. Returns None if no data."""
    dfs = []
    for _, arrs in data.batch_get_columns_as_arrays(station_dobjs):
        df = pd.DataFrame(arrs)
        df["Station"] = station_id
        dfs.append(df[["Station", "TIMESTAMP", KPI_COL]].copy())

    if not dfs:
        return None

    kpi_df = pd.concat(dfs, ignore_index=True)
    kpi_df["TIMESTAMP"] = pd.to_datetime(kpi_df["TIMESTAMP"])
    kpi_df["Month"] = kpi_df["TIMESTAMP"].dt.to_period("M")

    monthly_kpi = (
        kpi_df
        .dropna(subset=[KPI_COL])
        .groupby(["Station", "Month"])[KPI_COL]
        .agg(
            n_valid=lambda x: x.str.isdigit().sum(),
            n_qc2=lambda x: (x == "2").sum(),
        )
        .reset_index()
    )
    monthly_kpi["percentage_qc2"] = 100 * monthly_kpi["n_qc2"] / monthly_kpi["n_valid"]
    return monthly_kpi


def _fetch_level2(disk: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, dict]:
    """Fetch Level-2 data incrementally.

    For each station, list its data objects (fast — metadata only). If the set
    of URIs matches the cached fingerprint, reuse the cached monthly stats.
    Only re-download and reprocess stations where the data has changed.

    Returns (kpi_pct, kpi_nvalid, kpi_nqc2, station_uri_lookup, updated_disk).
    """
    os_stations = [
        s for s in meta.list_stations(OCEAN_STATION)
        if s.id not in IGNORE_STATIONS
    ]
    selected_datatypes = [
        dt for dt in meta.list_datatypes()
        if dt.has_data_access
        and dt.project.label == "ICOS"
        and dt.theme.uri == "http://meta.icos-cp.eu/resources/themes/ocean"
        and dt.data_level == 2
    ]
    station_uri_lookup = {s.id: s.uri for s in os_stations}
    datatype_uris = [dt.uri for dt in selected_datatypes]

    cached_fingerprints: dict = disk.get("fingerprints", {})
    cached_station_data: dict = disk.get("station_data", {})

    updated_fingerprints = {}
    monthly_rows = []
    n_reprocessed = 0

    for i, station in enumerate(os_stations, start=1):
        station_id = station.id

        # Lightweight metadata-only call — no data download
        station_dobjs = meta.list_data_objects(
            datatype=datatype_uris, station=station.uri
        )
        current_fp = frozenset(str(d.uri) for d in station_dobjs)
        updated_fingerprints[station_id] = current_fp

        if not station_dobjs:
            logger.debug("No L2 data for %s", station_id)
            monthly_rows.append(pd.DataFrame({
                "Station": [station_id],
                "Month": [pd.Period.now("M")],
                "n_valid": [0], "n_qc2": [0],
                "percentage_qc2": [np.nan],
            }))
            continue

        if station_id in cached_fingerprints and current_fp == cached_fingerprints[station_id]:
            logger.info("Station %s (%d/%d) — unchanged, using cache",
                        station_id, i, len(os_stations))
            monthly_rows.append(cached_station_data[station_id])
            continue

        logger.info("Station %s (%d/%d) — data updated, reprocessing …",
                    station_id, i, len(os_stations))
        n_reprocessed += 1
        result = _process_station(station_id, station_dobjs)
        if result is not None:
            cached_station_data[station_id] = result
            monthly_rows.append(result)

    logger.info("Reprocessed %d/%d stations", n_reprocessed, len(os_stations))

    all_monthly = pd.concat(monthly_rows, ignore_index=True)
    full_months = pd.period_range(
        all_monthly["Month"].min(), all_monthly["Month"].max(), freq="M"
    )

    def pivot(col):
        return (
            all_monthly
            .pivot(index="Station", columns="Month", values=col)
            .reindex(columns=full_months)
        )

    updated_disk = {
        "fingerprints": updated_fingerprints,
        "station_data": cached_station_data,
    }
    return pivot("percentage_qc2"), pivot("n_valid"), pivot("n_qc2"), station_uri_lookup, updated_disk


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_data(force: bool = False) -> dict:
    """Return cached data dict, refreshing if stale or forced."""
    global _cache, _cache_ts

    if _cache and not force and not _is_stale():
        return _cache

    logger.info("Fetching data from ICOS Carbon Portal …")
    t0 = time.time()

    try:
        nrt_df = _fetch_nrt()
        nrt_latest, nrt_urls, nrt_start = _build_nrt_lookups(nrt_df)

        l2_latest_df = _fetch_l2_latest()
        l2_latest, l2_urls = _build_l2_latest_lookups(l2_latest_df)

        disk = _load_disk_cache()
        kpi_pct, kpi_nvalid, kpi_nqc2, station_uri_lookup, updated_disk = _fetch_level2(disk)
        _save_disk_cache(updated_disk)

    except Exception as exc:
        logger.error("ICOS fetch failed: %s", exc, exc_info=True)
        if _cache:
            logger.warning("Returning stale cache from %s", _cache.get("last_refreshed"))
            return _cache
        raise RuntimeError(
            "ICOS data unavailable and no cached data exists. "
            "Check network access and ICOS Carbon Portal status."
        ) from exc

    _cache = {
        "kpi_pct": kpi_pct,
        "kpi_nvalid": kpi_nvalid,
        "kpi_nqc2": kpi_nqc2,
        "station_uri_lookup": station_uri_lookup,
        "l2_latest": l2_latest,
        "l2_urls": l2_urls,
        "nrt_latest": nrt_latest,
        "nrt_urls": nrt_urls,
        "nrt_start": nrt_start,
        "last_refreshed": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    }
    _cache_ts = time.time()

    logger.info("Data loaded in %.1fs — %d stations × %d months",
                time.time() - t0, kpi_pct.shape[0], kpi_pct.shape[1])
    return _cache
