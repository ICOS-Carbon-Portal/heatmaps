# OTC KPI Dashboard

An interactive dashboard for monitoring the data quality of fCO₂ measurements in Level 2 datasets, as well as the availability of Level 1 Near Real-Time (NRT) data from ICOS ocean stations.

The heatmap displays the monthly percentage of fCO₂ records flagged as good quality (QC = 2) relative to all valid measurements. Dark grey horizontal bars indicate the temporal coverage of the most recent Level 1 NRT data for stations that provide NRT observations. All data are sourced in real time from the [ICOS Carbon Portal](https://data.icos-cp.eu).

## Quick start

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the dashboard
python app.py
```

Open http://localhost:8050 in your browser.

You can pre-set the number of months shown by adding `?months=N` to the URL, e.g. http://localhost:8050/?months=6.

## Production deployment

```bash
gunicorn app:server --bind 0.0.0.0:8050 --workers 2 --timeout 300
```

The `--timeout 300` is important because the initial data fetch from ICOS can take a few minutes.

## Docker

```bash
docker build -t otc-kpi .
docker run -p 8050:8050 otc-kpi
```

## Configuration

Edit `config.py` to change:

- `CACHE_TTL` — how often data is re-fetched from ICOS (default: 6 hours)
- `IGNORE_STATIONS` — list of station IDs to exclude from the dashboard (e.g. `"BE-SOOP-Belgica"`). Add or remove entries to control which stations appear in the heatmap.
- `COLORMAPS` — available colour map options
- `DEFAULT_N_MONTHS` / `DEFAULT_CMAP` — initial widget values
- `DESCRIPTION` — descriptive text shown above the heatmap

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Dash app, layout, callbacks, figure generation |
| `data_fetch.py` | ICOS API calls, data processing, incremental disk cache |
| `config.py` | Constants, SPARQL queries, settings |
| `assets/style.css` | Custom styling (auto-loaded by Dash) |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container deployment |
| `l2_cache.pkl` | Auto-generated disk cache for Level 2 processed results |

## Credits

Developed by the [ICOS Carbon Portal](https://www.icos-cp.eu) with the assistance of Claude (Anthropic).
