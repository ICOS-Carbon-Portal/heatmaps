"""Run once to generate test fixtures from live SPARQL data.

hatch run python tests/create_fixtures.py
"""

import json
from pathlib import Path

import pandas as pd

from heatmaps.generator import build_heatmap_dataset, fetch_raw_data

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURES.mkdir(exist_ok=True)

YEARS = [2021, 2022, 2023]
N_STATIONS = 3


def stations_with_data_in_all_years(raw_data: pd.DataFrame) -> list[str]:
    """Return stations that have data in every year in YEARS."""
    common: set[str] | None = None
    for year in YEARS:
        start = pd.Timestamp(f"{year}-01-01", tz="UTC")
        end = pd.Timestamp(f"{year}-12-31 23:59:59", tz="UTC")
        mask = (raw_data.index >= start) & (raw_data.index <= end)
        year_stations = set(raw_data.loc[mask, "station"].dropna().unique())
        common = year_stations if common is None else common & year_stations
    return sorted(common or [])


for domain in ("atmosphere", "ecosystem"):
    prefix = "atm" if domain == "atmosphere" else "eco"
    print(f"Fetching {domain} data...")
    raw_data = fetch_raw_data(domain)

    all_stations = stations_with_data_in_all_years(raw_data)
    # Pick N stations spread evenly across the sorted list
    indices = [len(all_stations) * i // N_STATIONS for i in range(N_STATIONS)]
    selected = [all_stations[i] for i in indices]
    print(f"  Selected stations: {selected}")

    percentages_data: dict[str, dict[str, str]] = {}
    for station in selected:
        station_raw = raw_data[raw_data["station"] == station].copy()
        station_raw.to_parquet(FIXTURES / f"{prefix}_{station}_raw.parquet")

        percentages_data[station] = {}
        for year in YEARS:
            start = pd.Timestamp(f"{year}-01-01", tz="UTC")
            end = pd.Timestamp(f"{year}-12-31 23:59:59", tz="UTC")
            _, percentages = build_heatmap_dataset(
                raw_data=station_raw,
                start=start,
                end=end,
                bin_size="monthly",
            )
            percentages_data[station][str(year)] = percentages[0]
            print(f"  {station} {year}: {percentages[0]}")

    (FIXTURES / f"{prefix}_percentages.json").write_text(
        json.dumps(percentages_data, indent=2)
    )

print("Done.")
