# Standard imports
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Annotated

# Related imports
from yaspin import yaspin
import pandas as pd
import typer

# Local imports
from heatmaps.generator import (
    generate_heatmap,
    generate_period_heatmap,
    optimal_bin_size,
)
from heatmaps.report import generate_report


class Domain(str, Enum):
    ATMOSPHERE = "atmosphere"
    ECOSYSTEM = "ecosystem"


class BinSize(str, Enum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"


def parse_period(
    period: str,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Parse a period string into UTC start and end timestamps.

    Accepted formats:
      YYYY-YYYY       e.g. 2019-2024
      MMYYYY-MMYYYY   e.g. 012024-092024
      DDMMYYYY-DDMMYYYY  e.g. 01012020-31012020
    """
    parts = period.split("-")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid period '{period}'. "
            "Expected YYYY-YYYY, MMYYYY-MMYYYY, "
            "or DDMMYYYY-DDMMYYYY."
        )
    s, e = parts
    if len(s) != len(e):
        raise ValueError(f"Period parts have different lengths: '{period}'.")
    try:
        if len(s) == 4:
            start = pd.Timestamp(f"{s}-01-01", tz="UTC")
            end = pd.Timestamp(f"{e}-12-31 23:59:59", tz="UTC")
        elif len(s) == 6:
            s_month, s_year = int(s[:2]), int(s[2:])
            e_month, e_year = int(e[:2]), int(e[2:])
            start = pd.Timestamp(year=s_year, month=s_month, day=1, tz="UTC")
            last_day = pd.Timestamp(
                year=e_year, month=e_month, day=1, tz="UTC"
            ) + pd.offsets.MonthEnd(0)
            end = last_day.replace(hour=23, minute=59, second=59)
        elif len(s) == 8:
            s_day, s_mon, s_yr = int(s[:2]), int(s[2:4]), int(s[4:])
            e_day, e_mon, e_yr = int(e[:2]), int(e[2:4]), int(e[4:])
            start = pd.Timestamp(year=s_yr, month=s_mon, day=s_day, tz="UTC")
            end = pd.Timestamp(
                year=e_yr,
                month=e_mon,
                day=e_day,
                hour=23,
                minute=59,
                second=59,
                tz="UTC",
            )
        else:
            raise ValueError(
                f"Invalid period '{period}'. "
                "Expected YYYY-YYYY, MMYYYY-MMYYYY, "
                "or DDMMYYYY-DDMMYYYY."
            )
    except Exception as exc:
        raise ValueError(f"Could not parse period '{period}': {exc}") from exc
    if start >= end:
        raise ValueError(f"Period start must be before end: '{period}'.")
    return start, end


def _run_report(year: int, output_root: Path, cache_dir: Path | None) -> None:
    with yaspin(text="Preparing report") as spinner:
        result = generate_report(
            year=year,
            output_root=output_root,
            cache_dir=cache_dir,
            progress=lambda message: setattr(spinner, "text", message),
        )
        spinner.text = "Report generated"
        spinner.ok("✔")
    total = (
        len(result.standalone_paths)
        + len(result.cumulative_paths)
        + len(result.table_paths)
    )
    typer.echo(f"Generated {total} report files.")


def main(
    ctx: typer.Context,
    report: Annotated[
        int | None,
        typer.Option(
            "--report",
            help="Generate the full yearly report bundle for YEAR.",
            metavar="YEAR",
        ),
    ] = None,
    year: Annotated[
        int | None,
        typer.Option(
            "--year",
            help="Calendar year to generate (single heatmap mode).",
            metavar="YEAR",
        ),
    ] = None,
    period: Annotated[
        str | None,
        typer.Option(
            "--period",
            help=(
                "Time period for heatmap. Formats: "
                "YYYY-YYYY, MMYYYY-MMYYYY, "
                "or DDMMYYYY-DDMMYYYY."
            ),
            metavar="PERIOD",
        ),
    ] = None,
    domain: Annotated[
        Domain | None,
        typer.Option(
            "--domain",
            help="Heatmap domain.",
        ),
    ] = None,
    binning: Annotated[
        BinSize | None,
        typer.Option(
            "--bin",
            help=(
                "Time bin size. Auto-detected for --period, "
                "defaults to monthly for --year."
            ),
        ),
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option(
            "--cache-dir",
            help=(
                "Directory for caching fetched data. "
                "Reads from cache when available; "
                "writes to cache after fetching."
            ),
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir",
            help=(
                "Base directory for output (relative to current working directory). "
                "Files are written to a timestamped subdirectory, "
                "e.g. output/20260311T142305/. "
                "[default: output/<timestamp>/]"
            ),
            show_default=False,
        ),
    ] = Path("output"),
) -> None:
    """Generate ICOS raw data coverage heatmaps."""
    if report is None and year is None and period is None and domain is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    output_root = output_dir / timestamp

    if report is not None:
        _run_report(year=report, output_root=output_root, cache_dir=cache_dir)
        return

    if domain is None:
        raise typer.BadParameter("--domain is required unless --report is used.")

    if period is not None:
        try:
            start, end = parse_period(period)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        resolved_bin = (
            binning.value if binning is not None else optimal_bin_size(start, end)
        )
        with yaspin(text="Generating heatmap") as spinner:
            output_path = generate_period_heatmap(
                domain=domain.value,
                start=start,
                end=end,
                bin_size=resolved_bin,
                output_dir=output_root,
                cache_dir=cache_dir,
            )
            spinner.text = "Heatmap generated"
            spinner.ok("✔")
        typer.echo(f"Generated {output_path}.")
        return

    if year is None:
        raise typer.BadParameter(
            "--year is required when --report and --period are not used."
        )
    resolved_bin = binning.value if binning is not None else "monthly"
    with yaspin(text="Generating heatmap") as spinner:
        output_path = generate_heatmap(
            domain=domain.value,
            year=year,
            bin_size=resolved_bin,
            output_dir=output_root,
            cache_dir=cache_dir,
        )
        spinner.text = "Heatmap generated"
        spinner.ok("✔")
    typer.echo(f"Generated {output_path}.")


app = typer.Typer(no_args_is_help=True)
app.command()(main)


def run() -> None:
    """Run the heatmaps CLI."""
    app()


if __name__ == "__main__":
    run()
