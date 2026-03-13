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

from config import COLORMAPS, DEFAULT_N_MONTHS, DEFAULT_CMAP
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
logger.info("Initial data load …")
_data = load_data()
_kpi_pct = _data["kpi_pct"]
ALL_MONTHS = list(_kpi_pct.columns)
N_MONTHS_TOTAL = len(ALL_MONTHS)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = html.Div([

    html.H1("OTC KPI Dashboard", style={"textAlign": "center", "marginTop": 20}),

    html.P(
        "",
        id="last-refreshed",
        style={"textAlign": "center", "color": "#666", "fontSize": 13},
    ),

    # Controls
    html.Div([
        html.Div([
            html.Label("Last N months:", style={"fontWeight": "bold"}),
            dcc.Input(
                id="n-months",
                type="number",
                min=1, max=N_MONTHS_TOTAL,
                value=DEFAULT_N_MONTHS,
                debounce=True,
                style={"width": 80, "marginLeft": 8},
            ),
        ], style={"display": "inline-block", "marginRight": 30}),

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

    # Heatmap
    dcc.Loading(
        dcc.Graph(id="heatmap", config={"displayModeBar": True}),
        type="circle",
    ),

    # Link table
    html.Details([
        html.Summary(
            "Station & NRT links (click to expand)",
            style={"fontWeight": "bold", "cursor": "pointer", "fontSize": 14},
        ),
        html.Div(id="link-table"),
    ], style={"margin": "10px 40px 40px"}),

], style={"fontFamily": "Arial, sans-serif", "maxWidth": 1400, "margin": "0 auto"})


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
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
    station_uri_lookup = d["station_uri_lookup"]

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
                    else "No data"
                )
            )
            for c in range(len(col_labels))
        ]
        for r in range(len(stations))
    ]

    nrt_labels = [nrt_latest.get(s, "—") for s in stations]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=col_labels,
        y=stations,
        colorscale=cmap_name,
        zmin=0, zmax=100,
        text=cell_text,
        texttemplate="%{text}",
        textfont=dict(size=10),
        hovertext=hover,
        hoverinfo="text",
        showscale=False,
        xgap=1, ygap=1,
    ))

    fig.update_layout(
        title=dict(
            text=(
                f"OTC KPI – fCO2 QC2 %  |  Last {n} month{'s' if n != 1 else ''}"
                f"  ({col_labels[0]} → {col_labels[-1]})"
            ),
            font=dict(size=14),
        ),
        xaxis=dict(tickangle=-45, side="bottom", title="Month"),
        yaxis=dict(autorange="reversed", title="Station"),
        yaxis2=dict(
            overlaying="y",
            side="right",
            range=[len(stations) - 0.5, -0.5],
            tickmode="array",
            tickvals=list(range(len(stations))),
            ticktext=nrt_labels,
            title="Latest NRT End Date",
            showgrid=False,
        ),
        height=max(400, 36 * len(stations) + 140),
        margin=dict(l=200, r=200, t=70, b=90),
        paper_bgcolor="white",
        plot_bgcolor="#f8f8f8",
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

    # Build link table
    table_rows = []
    for s in stations:
        s_uri = station_uri_lookup.get(s, "")
        nrt_date = nrt_latest.get(s)
        nrt_url = nrt_urls.get(s)

        station_cell = (
            html.A(s, href=s_uri, target="_blank") if s_uri
            else html.Span(s)
        )
        nrt_cell = (
            html.A(nrt_date, href=nrt_url, target="_blank") if nrt_date and nrt_url
            else html.Span("—")
        )
        table_rows.append(html.Tr([html.Td(station_cell), html.Td(nrt_cell)]))

    link_table = html.Table(
        [
            html.Thead(html.Tr([
                html.Th("Station", style={"textAlign": "left", "borderBottom": "1px solid #ccc"}),
                html.Th("Latest NRT Data Object", style={"textAlign": "left", "borderBottom": "1px solid #ccc"}),
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
    app.run(debug=debug, host="0.0.0.0", port=8050)
