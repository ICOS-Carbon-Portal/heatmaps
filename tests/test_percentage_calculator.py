import json
from pathlib import Path

import pandas as pd
import pytest

from heatmaps.generator import (
    _percentage_calculator,
    build_heatmap_dataset,
    fetch_raw_data,
)

FIXTURES = Path(__file__).parent / "fixtures"


def calc(series):
    return _percentage_calculator(series)


def _percentages_for_station(
    raw_data: pd.DataFrame, station: str, year: int
) -> str:
    station_raw = raw_data[raw_data["station"] == station].copy()
    _, percentages = build_heatmap_dataset(
        raw_data=station_raw,
        start=pd.Timestamp(f"{year}-01-01", tz="UTC"),
        end=pd.Timestamp(f"{year}-12-31 23:59:59", tz="UTC"),
        bin_size="monthly",
    )
    return percentages[0]


@pytest.mark.network
def test_atmosphere_stations_match_fixture():
    fixture = json.loads((FIXTURES / "atm_percentages.json").read_text())
    raw = fetch_raw_data("atmosphere")
    for station, year_data in fixture.items():
        for year_str, expected in year_data.items():
            actual = _percentages_for_station(raw, station, int(year_str))
            assert actual == expected, f"atmosphere / {station} / {year_str}"


@pytest.mark.network
def test_ecosystem_stations_match_fixture():
    fixture = json.loads((FIXTURES / "eco_percentages.json").read_text())
    raw = fetch_raw_data("ecosystem")
    for station, year_data in fixture.items():
        for year_str, expected in year_data.items():
            actual = _percentages_for_station(raw, station, int(year_str))
            assert actual == expected, f"ecosystem / {station} / {year_str}"
