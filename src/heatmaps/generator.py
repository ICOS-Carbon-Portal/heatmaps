# Standard imports
from pathlib import Path

# Related imports
from icoscp.sparql.runsparql import RunSparql
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


CPMETA_SPECS = {
    "atmosphere": (
        "<http://meta.icos-cp.eu/resources/cpmeta/atcLosGatosL0DataObject>"
        " "
        "<http://meta.icos-cp.eu/resources/cpmeta/atcPicarroL0DataObject>"
    ),
    "ecosystem": (
        "<http://meta.icos-cp.eu/resources/cpmeta/etcEddyFluxRawSeriesCsv>"
        " "
        "<http://meta.icos-cp.eu/resources/cpmeta/etcEddyFluxRawSeriesBin>"
    ),
}

DOMAIN_FILE_PREFIXES = {
    "atmosphere": "atm",
    "ecosystem": "eco",
}

BIN_SETTINGS = {
    "monthly": {
        "freq": "ME",
        "label": "month",
        "formatter": "%m-%y",
        "suffix": "m",
    },
    "weekly": {
        "freq": "W",
        "label": "week",
        "formatter": "%U-%y",
        "suffix": "w",
    },
}

RAW_DATA_QUERY = """prefix cpmeta: <http://meta.icos-cp.eu/ontologies/cpmeta/>
prefix prov: <http://www.w3.org/ns/prov#>
select ?timeStart ?timeEnd ?fileName
where {
  VALUES ?spec {#obj_spec}
  ?dobj cpmeta:hasObjectSpec ?spec .
  ?dobj cpmeta:hasSizeInBytes ?size .
  ?dobj cpmeta:hasName ?fileName .
  ?dobj cpmeta:wasSubmittedBy/prov:endedAtTime ?submTime .
  ?dobj cpmeta:hasStartTime | (cpmeta:wasAcquiredBy/prov:startedAtTime)
    ?timeStart .
  ?dobj cpmeta:hasEndTime | (cpmeta:wasAcquiredBy/prov:endedAtTime) ?timeEnd .
  FILTER NOT EXISTS {[] cpmeta:isNextVersionOf ?dobj}
}
order by desc(?submTime)
"""

HEATMAP_KWARGS = {
    "center": 95,
    "vmin": 0,
    "vmax": 100,
    "linewidths": 0.07,
    "xticklabels": 1,
}


def _percentage_calculator(interval: pd.Series) -> float:
    """Work out what percentage of a time period a station has data for.

    Each station sends data at its own pace and in different chunk sizes,
    so we first look at the incoming files to get a feel for what is normal
    for that station. We then compare how much data actually arrived against
    how much we would expect if the station had been running the whole time.

    To find a reliable "normal" chunk size we try three approaches and pick
    the most cautious result:
      1. The median of all chunk sizes.
      2. The median of the smaller chunks only, so a few very large
         files do not throw off the result.
      3. The average chunk size, used only as a last resort.

    Returns NaN if the interval contains no data, 0 if the expected unit
    cannot be determined, and caps the result at 100.
    """
    if interval.isnull().all():
        return float("nan")

    max_days: list[float] = []
    current_max_day = interval.median().round(freq="h").days
    max_days.append(current_max_day)

    if len(interval) > 1:
        current_max_day = (
            interval.nsmallest(len(interval) // 2).median().round(freq="h").days
        )
        max_days.append(current_max_day)

    if not current_max_day:
        current_max_day = round(
            (interval.mean().round(freq="h").seconds // 3600) / 24,
            1,
        )
        max_days.append(current_max_day)

    max_day = (
        min([value for value in max_days if value > 0])
        if not all(value == 0 for value in max_days)
        else 0
    )
    summation = interval.sum()
    total = pd.Timedelta(days=len(interval)) * max_day
    percentage = round(100 * (summation / total), 1) if max_day else 0
    return 100 if percentage > 100 else percentage


def build_bin_index(
    start: pd.Timestamp,
    end: pd.Timestamp,
    bin_size: str,
) -> pd.DatetimeIndex:
    return pd.date_range(
        start=start,
        end=end,
        freq=BIN_SETTINGS[bin_size]["freq"],
        tz="UTC",
    )


def fetch_raw_data(
    domain: str,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    if cache_dir is not None:
        cache_file = cache_dir / f"{domain}.parquet"
        if cache_file.exists():
            return pd.read_parquet(cache_file)

    raw_data = RunSparql(
        sparql_query=RAW_DATA_QUERY.replace("#obj_spec", CPMETA_SPECS[domain]),
        output_format="pandas",
    ).run()
    if isinstance(raw_data, tuple) or raw_data is False:
        details = raw_data[1] if isinstance(raw_data, tuple) else "no data"
        raise RuntimeError(f"SPARQL query failed for '{domain}': {details}")
    if raw_data.empty:
        raise ValueError(f"SPARQL query returned no rows for '{domain}'.")

    normalized = raw_data.assign(
        timeStart=pd.to_datetime(raw_data["timeStart"], utc=True),
        timeEnd=pd.to_datetime(raw_data["timeEnd"], utc=True),
    )
    normalized["period"] = normalized["timeEnd"] - normalized["timeStart"]
    normalized["station"] = normalized["fileName"].str.split("_").str[0]
    result = normalized.set_index("timeStart")[["station", "period"]]

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        result.to_parquet(cache_file)

    return result


def build_heatmap_dataset(
    raw_data: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    bin_size: str,
) -> tuple[pd.DataFrame, list[str]]:
    periods_by_station = raw_data.groupby("station", sort=True)["period"]
    stations = list(periods_by_station.groups)
    if not stations:
        raise ValueError("No stations returned for the selected data range.")

    bin_index = build_bin_index(start=start, end=end, bin_size=bin_size)
    empty_daily_index = pd.date_range(start=start, end=end, freq="D", tz="UTC")
    binned_data: dict[str, pd.Series] = {}
    percentages: list[str] = []

    for station in stations:
        station_periods = periods_by_station.get_group(station)
        station_series = station_periods[
            (station_periods.index >= start) & (station_periods.index <= end)
        ]
        if station_series.empty:
            empty_daily = pd.Series(
                data=float("nan"),
                index=empty_daily_index,
                dtype="float64",
            )
            binned_series = (
                empty_daily.resample(BIN_SETTINGS[bin_size]["freq"])
                .apply(_percentage_calculator)
                .reindex(bin_index)
            )
            percentages.append("  No Data")
        else:
            daily_series = station_series.resample("D").sum()
            binned_series = (
                daily_series.resample(BIN_SETTINGS[bin_size]["freq"])
                .apply(_percentage_calculator)
                .reindex(bin_index)
            )
            non_null_bins = binned_series.dropna()
            average_percentage = (
                round(non_null_bins.mean(), 1) if not non_null_bins.empty else 0.0
            )
            percentages.append(f"  {average_percentage} %")

        binned_data[station] = binned_series

    parsed_data = pd.DataFrame(binned_data, index=bin_index)
    parsed_data.index = parsed_data.index.strftime(BIN_SETTINGS[bin_size]["formatter"])
    return parsed_data.transpose(), percentages


def render_heatmap(
    parsed_data: pd.DataFrame,
    percentages: list[str],
    domain: str,
    year_label: str,
    bin_size: str,
) -> plt.Figure:
    n_bins = len(parsed_data.columns)
    fig_width = max(16, n_bins * 0.35)
    x_fontsize = max(9, min(16, round(14 * (35 / n_bins) ** 0.25) + 2))
    fig, ax = plt.subplots(figsize=(fig_width, 10))
    sns.heatmap(
        parsed_data,
        ax=ax,
        cbar=False,
        yticklabels=parsed_data.index,
        **HEATMAP_KWARGS,
    )
    ax.yaxis.label.set_color("silver")
    ax.set_ylabel(
        ylabel="Stations",
        fontdict={"fontsize": 18, "fontweight": "bold"},
        labelpad=5,
    )
    ax.set_yticklabels(
        ax.get_yticklabels(),
        fontdict={"fontsize": 10, "fontweight": 400},
    )
    ax.set_xticklabels(
        ax.get_xticklabels(),
        rotation=80,
        fontdict={"fontsize": x_fontsize},
    )

    ax2 = ax.twinx()
    sns.heatmap(
        parsed_data,
        ax=ax2,
        cmap="coolwarm_r",
        cbar_kws={"pad": 0.12},
        yticklabels=percentages,
        **HEATMAP_KWARGS,
    )
    ax2.yaxis.label.set_color("silver")
    ax2.set_yticklabels(
        ax2.get_yticklabels(),
        fontdict={"fontsize": 10, "fontweight": 400},
    )
    ax2.set_ylabel(
        ylabel=f"Total Percentages for {year_label}",
        fontdict={"fontsize": 18, "fontweight": "bold"},
        labelpad=10,
    )
    plt.title(
        label=(
            f"\nICOS | {domain} raw data\n"
            f"coverage per {BIN_SETTINGS[bin_size]['label']} and station\n"
            f"for {year_label}"
        ),
        fontdict={
            "fontsize": 20,
            "fontweight": 600,
            "verticalalignment": "baseline",
            "horizontalalignment": "center",
        },
        y=1.04,
        pad=20.0,
    )
    fig.text(x=0, y=0, s="\n\n")
    fig.text(x=0.92, y=0.92, s=" ")
    fig.tight_layout()
    return fig


def optimal_bin_size(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """Return the best bin size for the given time range.

    Uses weekly binning for periods shorter than 60 days,
    monthly otherwise.
    """
    return "weekly" if (end - start).days < 60 else "monthly"


def generate_heatmap(
    domain: str,
    year: int,
    bin_size: str,
    output_dir: Path,
    raw_data: pd.DataFrame | None = None,
    cache_dir: Path | None = None,
) -> Path:
    start = pd.Timestamp(f"{year}-01-01", tz="UTC")
    end = pd.Timestamp(f"{year}-12-31 23:59:59", tz="UTC")
    output_dir.mkdir(parents=True, exist_ok=True)
    source_data = (
        raw_data if raw_data is not None else fetch_raw_data(domain, cache_dir)
    )
    parsed_data, percentages = build_heatmap_dataset(
        raw_data=source_data,
        start=start,
        end=end,
        bin_size=bin_size,
    )
    suffix = BIN_SETTINGS[bin_size]["suffix"]
    output_path = output_dir / f"heatmap_{domain}_{suffix}_{year}.png"
    fig = render_heatmap(
        parsed_data=parsed_data,
        percentages=percentages,
        domain=domain,
        year_label=str(year),
        bin_size=bin_size,
    )
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return output_path


def generate_period_heatmap(
    domain: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    bin_size: str,
    output_dir: Path,
    cache_dir: Path | None = None,
) -> Path:
    source_data = fetch_raw_data(domain, cache_dir)
    parsed_data, percentages = build_heatmap_dataset(
        raw_data=source_data,
        start=start,
        end=end,
        bin_size=bin_size,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = BIN_SETTINGS[bin_size]["suffix"]
    period_label = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
    output_path = output_dir / f"heatmap_{domain}_{suffix}_{period_label}.png"
    year_label = f"{start.strftime('%b %Y')} \u2013 {end.strftime('%b %Y')}"
    fig = render_heatmap(
        parsed_data=parsed_data,
        percentages=percentages,
        domain=domain,
        year_label=year_label,
        bin_size=bin_size,
    )
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return output_path
