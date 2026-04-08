"""
OTC KPI Dashboard — Dash application.

Run:
    python app.py            # development
    gunicorn app:server      # production
"""

import logging
import os
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from dash import Dash, dcc, html, Input, Output, callback, ctx
from urllib.parse import parse_qs, urlparse

from config import COLORMAPS, DEFAULT_N_MONTHS, DEFAULT_CMAP, DESCRIPTION
from data_fetch import load_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App init
# ---------------------------------------------------------------------------
app = Dash(
    __name__,
    title="OTC KPI Dashboard",
    update_title="Loading…",
)
server = app.server  # exposed for gunicorn

# ---------------------------------------------------------------------------
# Fetch data at startup
# ---------------------------------------------------------------------------
# Only run the expensive data load in the actual server process.
# When debug=True, Werkzeug spawns a watcher (parent) + server (child).
# WERKZEUG_RUN_MAIN="true" is set only in the child — skip loading in the parent
# to avoid fetching data twice on startup.
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or os.environ.get("DASH_DEBUG", "false").lower() != "true":
    logger.info("Initial data load …")
    _data = load_data()
    _kpi_pct = _data["kpi_pct"]
    ALL_MONTHS = list(_kpi_pct.columns)
    N_MONTHS_TOTAL = len(ALL_MONTHS)
else:
    _data = None
    _kpi_pct = None
    ALL_MONTHS = []
    N_MONTHS_TOTAL = 0

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = html.Div([

    dcc.Location(id="url", refresh=False),

    html.H1("OTC KPI Dashboard", style={"textAlign": "center", "marginTop": 20}),

    html.P(
        "",
        id="last-refreshed",
        style={"textAlign": "center", "color": "#666", "fontSize": 13},
    ),

    # Controls
    html.Div([
        html.Div([
            html.Span("Last", style={"fontWeight": "bold"}),
            dcc.Input(
                id="n-months",
                type="number",
                min=1, max=N_MONTHS_TOTAL,
                value=DEFAULT_N_MONTHS,
                debounce=True,
                style={"width": 70, "margin": "0 8px"},
            ),
            html.Span("months", style={"fontWeight": "bold"}),
        ], style={"display": "inline-flex", "alignItems": "center", "marginRight": 30}),

        html.Div([
            html.Label("Colour map:", style={"fontWeight": "bold"}),
            dcc.Dropdown(
                id="cmap",
                options=[{"label": c, "value": c} for c in COLORMAPS],
                value=DEFAULT_CMAP,
                clearable=False,
                style={"width": 160, "display": "inline-block", "marginLeft": 8,
                        "verticalAlign": "middle"},
            ),
        ], style={"display": "inline-block"}),

        html.Div([
            html.Button(
                "Refresh Data",
                id="refresh-btn",
                n_clicks=0,
                style={"marginLeft": 30, "verticalAlign": "middle"},
            ),
        ], style={"display": "inline-block"}),
    ], style={"textAlign": "center", "margin": "16px 0"}),

    # Description
    html.Details([
        html.Summary(
            "Explanatory text (click to expand)",
            style={"fontWeight": "bold", "cursor": "pointer", "fontSize": 16},
        ),
        dcc.Markdown(
            DESCRIPTION or "*[ Description placeholder — edit DESCRIPTION in config.py ]*",
            dangerously_allow_html=True,
            style={
                "color": "#888" if not DESCRIPTION else "#333",
                "fontSize": 16,
                "textAlign": "justify",
                "margin": "8px 40px 16px",
            },
        ),
    ], style={"margin": "10px 40px 16px"}),

    # Heatmap
    dcc.Loading(
        dcc.Graph(id="heatmap", config={"displayModeBar": True}),
        type="circle",
    ),

    # Link table
    html.Details([
        html.Summary(
            "Links to station landing pages and data objects (click to expand)",
            style={"fontWeight": "bold", "cursor": "pointer", "fontSize": 16},
        ),
        html.Div(id="link-table"),
    ], style={"margin": "10px 40px 40px"}),

], style={"maxWidth": 1400, "margin": "0 auto"})


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
@callback(
    Output("n-months", "value"),
    Input("url", "search"),
    prevent_initial_call=False,
)
def set_months_from_url(search):
    if search:
        params = parse_qs(search.lstrip("?"))
        if "months" in params:
            try:
                n = int(params["months"][0])
                return max(1, min(n, N_MONTHS_TOTAL or n))
            except ValueError:
                pass
    return DEFAULT_N_MONTHS


@callback(
    Output("heatmap", "figure"),
    Output("link-table", "children"),
    Output("last-refreshed", "children"),
    Input("n-months", "value"),
    Input("cmap", "value"),
    Input("refresh-btn", "n_clicks"),
)
def update_heatmap(n, cmap_name, _refresh_clicks):
    force = ctx.triggered_id == "refresh-btn"
    d = load_data(force=force)
    kpi_pct = d["kpi_pct"]
    kpi_nvalid = d["kpi_nvalid"]
    kpi_nqc2 = d["kpi_nqc2"]
    nrt_latest = d["nrt_latest"]
    nrt_urls = d["nrt_urls"]
    nrt_start = d["nrt_start"]
    station_uri_lookup = d["station_uri_lookup"]
    l2_latest = d["l2_latest"]
    l2_urls = d["l2_urls"]

    n = max(1, min(n or DEFAULT_N_MONTHS, len(kpi_pct.columns)))

    cols = list(kpi_pct.columns)[-n:]
    pct = kpi_pct[cols]
    nv = kpi_nvalid[cols]
    nq = kpi_nqc2[cols]


    stations = list(pct.index)
    col_labels = [str(c) for c in cols]
    z = pct.values.tolist()

    cell_text = [
        [f"{v:.0f}%" if pd.notna(v) else "" for v in row]
        for row in z
    ]

    # Per-station index of the last month that has Level-2 data
    last_data_col = [
        max((i for i, v in enumerate(row) if pd.notna(v)), default=-1)
        for row in z
    ]

    hover = [
        [
            (
                f"<b>{stations[r]}</b><br>"
                f"Month: {col_labels[c]}<br>"
                + (
                    f"QC2: {z[r][c]:.1f}%<br>"
                    f"Valid points: {int(nv.iloc[r, c])}<br>"
                    f"QC2 points: {int(nq.iloc[r, c])}"
                    if pd.notna(z[r][c])
                    else ("No level 2 data published" if last_data_col[r] == -1
                          else ("No level 2 since last release" if c > last_data_col[r] else "No level 2 data"))
                )
            )
            for c in range(len(col_labels))
        ]
        for r in range(len(stations))
    ]

    nrt_labels = [
        f"{nrt_start.get(s, '?')} → {nrt_latest.get(s, '?')[:10]}"
        if nrt_latest.get(s) else "—"
        for s in stations
    ]

    show_numbers = n <= 24

    fig = go.Figure(go.Heatmap(
        z=z,
        x=col_labels,
        y=stations,
        colorscale=cmap_name,
        zmin=0, zmax=100,
        text=cell_text,
        texttemplate="%{text}" if show_numbers else "",
        textfont=dict(size=12, family="Arial, sans-serif"),
        hovertext=hover,
        hoverinfo="text",
        showscale=not show_numbers,
        colorbar=dict(
            orientation="h",
            x=0.5, xanchor="center",
            y=-0.18, yanchor="top",
            thickness=15,
            len=0.5,
            title=dict(text="%", side="bottom"),
            tickfont=dict(size=12, family="Arial, sans-serif"),
        ),
        xgap=1, ygap=1,
    ))

    fig.update_layout(
        font=dict(family="Arial, sans-serif", size=13),
        title=dict(
            text=(
                f"<b>Percentage of good quality fCO\u2082 measurements in Level 2 data</b>"
                f"  |  Last {n} month{'s' if n != 1 else ''}"
                f"  ({col_labels[0]} → {col_labels[-1]})"
            ),
            font=dict(size=18, family="Arial, sans-serif"),
        ),
        xaxis=dict(
            tickangle=0, side="bottom", title="<b>Month</b>",
            tickfont=dict(size=13, family="Arial, sans-serif"),
            title_font=dict(size=15, family="Arial, sans-serif"),
            showgrid=False,
        ),
        xaxis2=dict(
            overlaying="x",
            side="bottom",
            type="date",
            range=[
                pd.Period(col_labels[0], "M").start_time.strftime("%Y-%m-%d"),
                (pd.Period(col_labels[-1], "M").end_time
                 + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            ],
            showticklabels=False,
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            range=[len(stations) - 0.5, -0.5],
            title="<b>Station</b>",
            tickfont=dict(size=13, family="Arial, sans-serif"),
            title_font=dict(size=15, family="Arial, sans-serif"),
            showgrid=False,
            zeroline=False,
        ),
        yaxis2=dict(
            overlaying="y",
            side="right",
            range=[len(stations) - 0.5, -0.5],
            tickmode="array",
            tickvals=list(range(len(stations))),
            ticktext=nrt_labels,
            title="",
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=13, family="Arial, sans-serif"),
        ),
        height=max(400, 36 * len(stations) + 140),
        margin=dict(l=200, r=200, t=70, b=90),
        paper_bgcolor="#fafafa",
        plot_bgcolor="#fafafa",
    )

    fig.add_annotation(
        text="<b>Latest NRT Data</b>",
        xref="paper", yref="paper",
        x=1.02, y=1.01,
        xanchor="left", yanchor="bottom",
        showarrow=False,
        font=dict(size=15, family="Arial, sans-serif"),
    )

    # Invisible trace to activate yaxis2
    fig.add_trace(go.Scatter(
        x=[None] * len(stations),
        y=list(range(len(stations))),
        yaxis="y2",
        mode="markers",
        marker=dict(opacity=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Semi-transparent NRT bars at day resolution, plotted on xaxis2 (date type).
    # Clipped to the visible date window derived from the displayed month columns.
    x2_start = pd.Period(col_labels[0], "M").start_time.strftime("%Y-%m-%d")
    x2_end = (pd.Period(col_labels[-1], "M").end_time + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    for station in stations:
        start_str = nrt_start.get(station)
        end_str = nrt_latest.get(station)
        if not start_str or not end_str:
            continue  # no L1 data for this station

        # Clip to the visible date window
        bar_start = max(start_str[:10], x2_start)
        bar_end = min(end_str[:10], x2_end)
        if bar_start > bar_end:
            continue  # NRT period fully outside the visible range

        fig.add_trace(go.Scatter(
            x=[bar_start, bar_end],
            y=[station, station],
            xaxis="x2",
            mode="lines",
            line=dict(color="rgba(105,105,105,0.4)", width=10),
            showlegend=False,
            hovertemplate=(
                f"<b>{station}</b><br>"
                f"NRT L1 coverage<br>"
                f"{start_str[:10]} → {end_str[:10]}"
                "<extra></extra>"
            ),
        ))

    # Build link table
    table_rows = []
    th_style = {"textAlign": "left", "borderBottom": "1px solid #ccc", "paddingRight": "24px"}
    td_style = {"paddingRight": "24px"}
    for s in stations:
        s_uri = station_uri_lookup.get(s, "")
        l2_date = l2_latest.get(s)
        l2_url = l2_urls.get(s)
        nrt_date = nrt_latest.get(s)
        nrt_url = nrt_urls.get(s)

        station_cell = (
            html.A(s, href=s_uri, target="_blank") if s_uri
            else html.Span(s)
        )
        l2_cell = (
            html.A(l2_date, href=l2_url, target="_blank") if l2_date and l2_url
            else html.Span(l2_date if l2_date else "—")
        )
        nrt_cell = (
            html.A(nrt_date, href=nrt_url, target="_blank") if nrt_date and nrt_url
            else html.Span("—")
        )
        table_rows.append(html.Tr([
            html.Td(station_cell, style=td_style),
            html.Td(l2_cell, style=td_style),
            html.Td(nrt_cell, style=td_style),
        ]))

    link_table = html.Table(
        [
            html.Thead(html.Tr([
                html.Th("Station", style=th_style),
                html.Th("Latest L2 Release", style=th_style),
                html.Th("Latest NRT Data", style=th_style),
            ])),
            html.Tbody(table_rows),
        ],
        style={"borderCollapse": "collapse", "fontSize": 13, "marginTop": 6},
    )

    return fig, link_table, f"Data last refreshed: {d['last_refreshed']}"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    debug = os.environ.get("DASH_DEBUG", "false").lower() == "true"
    logger.info("Dashboard available at http://127.0.0.1:8050")
    app.run(debug=debug, dev_tools_ui=False, dev_tools_props_check=False, host="0.0.0.0", port=8050)
