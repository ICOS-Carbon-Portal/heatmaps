# OTC KPI Dashboard

Interactive heatmap of monthly fCO₂ QC2 percentages across ICOS OTC ocean stations.

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
- `IGNORE_STATIONS` — stations to exclude
- `COLORMAPS` — available colour map options
- `DEFAULT_N_MONTHS` / `DEFAULT_CMAP` — initial widget values

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Dash app, layout, callbacks |
| `data_fetch.py` | ICOS API calls, data processing, in-memory cache |
| `config.py` | Constants, SPARQL query, settings |
| `assets/style.css` | Custom styling (auto-loaded by Dash) |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container deployment |
