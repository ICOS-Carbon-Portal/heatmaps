"""
Fetch and process ICOS OTC data.

All expensive ICOS API calls happen here. Results are cached in memory
and refreshed based on CACHE_TTL in config.py.
"""

import time
import logging
import pandas as pd
import numpy as np
from icoscp_core.icos import data, meta, OCEAN_STATION
from icoscp_core.sparql import as_string, as_uri

from config import IGNORE_STATIONS, KPI_COL, NRT_QUERY, CACHE_TTL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------
_cache: dict = {}
_cache_ts: float = 0.0


def _is_stale() -> bool:
    return (time.time() - _cache_ts) > CACHE_TTL


# ---------------------------------------------------------------------------
# NRT (Level 1)
# ---------------------------------------------------------------------------
def _fetch_nrt() -> pd.DataFrame:
    """Run the NRT SPARQL query and return a DataFrame with Station,
    DataEndTime (datetime), and DataObject (URL)."""
    rows = [
        {
            "Station": as_string("stationName", r),
            "DataEndTime": as_string("timeEnd", r),
            "DataObject": as_uri("dobj", r),
        }
        for r in meta.sparql_select(NRT_QUERY).bindings
    ]
    df = pd.DataFrame(rows)
    df["DataEndTime"] = pd.to_datetime(df["DataEndTime"])
    return df


def _build_nrt_lookups(nrt_df: pd.DataFrame) -> tuple[dict, dict]:
    """Return (nrt_latest, nrt_urls) dicts keyed by station name."""
    info = (
        nrt_df
        .sort_values("DataEndTime", ascending=False)
        .drop_duplicates(subset="Station", keep="first")
        .set_index("Station")
    )
    nrt_latest = info["DataEndTime"].dt.strftime("%Y-%m-%d %H:%M").to_dict()
    nrt_urls = info["DataObject"].to_dict()
    return nrt_latest, nrt_urls


# ---------------------------------------------------------------------------
# Level 2 KPI
# ---------------------------------------------------------------------------
def _fetch_level2() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Fetch Level-2 data for all stations, compute monthly KPI.

    Returns (kpi_pct, kpi_nvalid, kpi_nqc2, station_uri_lookup).
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
    station_uris = [s.uri for s in os_stations]
    datatype_uris = [dt.uri for dt in selected_datatypes]

    monthly_rows = []

    for i, station_uri in enumerate(station_uris, start=1):
        station_id = meta.get_station_meta(station_uri).id
        logger.info("Processing station %s (%d/%d) …", station_id, i, len(station_uris))
        station_dobjs = meta.list_data_objects(
            datatype=datatype_uris, station=station_uri
        )

        if not station_dobjs:
            logger.debug("  No Level-2 data objects found for %s", station_id)
            monthly_rows.append(pd.DataFrame({
                "Station": [station_id],
                "Month": [pd.Period.now("M")],
                "n_valid": [0], "n_qc2": [0],
                "percentage_qc2": [np.nan],
            }))
            continue

        dfs = []
        for _, arrs in data.batch_get_columns_as_arrays(station_dobjs):
            df = pd.DataFrame(arrs)
            df["Station"] = station_id
            dfs.append(df[["Station", "TIMESTAMP", KPI_COL]].copy())

        if not dfs:
            continue

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
        monthly_kpi["percentage_qc2"] = (
            100 * monthly_kpi["n_qc2"] / monthly_kpi["n_valid"]
        )
        monthly_rows.append(monthly_kpi)

    all_monthly = pd.concat(monthly_rows, ignore_index=True)

    full_months = pd.period_range(
        all_monthly["Month"].min(), all_monthly["Month"].max(), freq="M"
    )

    kpi_pct = (
        all_monthly
        .pivot(index="Station", columns="Month", values="percentage_qc2")
        .reindex(columns=full_months)
    )
    kpi_nvalid = (
        all_monthly
        .pivot(index="Station", columns="Month", values="n_valid")
        .reindex(columns=full_months)
    )
    kpi_nqc2 = (
        all_monthly
        .pivot(index="Station", columns="Month", values="n_qc2")
        .reindex(columns=full_months)
    )

    return kpi_pct, kpi_nvalid, kpi_nqc2, station_uri_lookup


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load_data(force: bool = False) -> dict:
    """Return cached data dict, refreshing if stale or forced.

    Keys: kpi_pct, kpi_nvalid, kpi_nqc2, station_uri_lookup,
          nrt_latest, nrt_urls, last_refreshed
    """
    global _cache, _cache_ts

    if _cache and not force and not _is_stale():
        return _cache

    logger.info("Fetching data from ICOS Carbon Portal …")
    t0 = time.time()

    try:
        nrt_df = _fetch_nrt()
        nrt_latest, nrt_urls = _build_nrt_lookups(nrt_df)
        kpi_pct, kpi_nvalid, kpi_nqc2, station_uri_lookup = _fetch_level2()
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
        "nrt_latest": nrt_latest,
        "nrt_urls": nrt_urls,
        "last_refreshed": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    }
    _cache_ts = time.time()

    elapsed = time.time() - t0
    logger.info(f"Data loaded in {elapsed:.1f}s — "
                f"{kpi_pct.shape[0]} stations × {kpi_pct.shape[1]} months")
    return _cache
