from pathlib import Path
from unittest.mock import patch

import pandas as pd
from typer.testing import CliRunner

from heatmaps.heatmap_cli import app

runner = CliRunner()


EXPECTED_OPTIONS = [
    "--report",
    "--year",
    "--period",
    "--domain",
    "--bin",
    "--cache-dir",
    "--output-dir",
    "--help",
]


def test_no_args_prints_help():
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Generate ICOS raw data coverage heatmaps" in result.output
    for opt in EXPECTED_OPTIONS:
        assert opt in result.output, f"missing option {opt!r} in no-args output"


def test_help_flag_prints_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Generate ICOS raw data coverage heatmaps" in result.output
    for opt in EXPECTED_OPTIONS:
        assert opt in result.output, f"missing option {opt!r} in --help output"
    no_args_result = runner.invoke(app, [])
    assert no_args_result.exit_code == 0
    assert result.output == no_args_result.output


def _minimal_raw_data(year: int = 2023) -> pd.DataFrame:
    """Minimal DataFrame matching the schema returned by fetch_raw_data."""
    dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "station": "TST",
            "period": pd.Timedelta(hours=24),
        },
        index=dates,
    )


def test_year_domain_generates_png(tmp_path: Path) -> None:
    with patch("heatmaps.generator.fetch_raw_data", return_value=_minimal_raw_data()):
        result = runner.invoke(
            app,
            [
                "--year",
                "2023",
                "--domain",
                "atmosphere",
                "--output-dir",
                str(tmp_path),
            ],
        )

    assert result.exit_code == 0, result.output
    pngs = list(tmp_path.rglob("*.png"))
    assert len(pngs) == 1
    assert pngs[0].stat().st_size > 0
    assert "heatmap_atmosphere_m_2023.png" in pngs[0].name
    assert str(pngs[0]) in result.output
