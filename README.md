# TerraTrend AI

**Investigate. Analyze. Discover.**

A global Earth-intelligence platform that lets anyone select any place on Earth and investigate its environmental conditions using real NASA, USGS and OpenStreetMap data — with a photorealistic 3D globe, a scientific analysis engine, and evidence-based interpretation.

🌍 **Live demo:** https://terratrend-ai.onrender.com
📦 **Source:** https://github.com/sukruthasraoo/Terratrend-ai

> Built for the NASA Space Apps Challenge 2026.

---

## The problem

NASA publishes petabytes of Earth-observation data, but asking a simple question such as *"Is my city getting hotter, and how sure are we?"* still requires knowing which dataset to use, how to download it, how to analyse it correctly, and how to interpret the result without overclaiming. TerraTrend AI closes that gap in one workflow:

**Select a location → discover datasets → explore conditions → analyse historical change → detect anomalies → compare regions → generate findings → export a report.**

## What it does

| Module | What you can do |
|---|---|
| **Earth Explorer** | Interactive CesiumJS globe with 15 NASA GIBS satellite layers (true colour, land-surface temperature, sea-surface temperature, precipitation, NDVI, fires, aerosols, snow, sea ice, soil moisture, night lights, CERES radiation). Search any country, state, city or coordinate; administrative boundaries are drawn from OpenStreetMap. A timeline scrubs imagery back to 2000. |
| **Live Monitor** | Near-real-time natural events from NASA EONET (wildfires, storms, volcanoes, floods, ice) and USGS earthquakes plotted on the globe with observation times, magnitudes, sensors and source links. NASA FIRMS fire detections plug in with a free key. |
| **Environmental Intelligence** | Nine investigation categories. Climate, water, energy, land and atmosphere pull monthly series from NASA POWER (MERRA-2 / CERES) for any point or region. Vegetation, ocean and cryosphere show imagery plus dataset discovery, honestly marked where numeric series need Earthdata login. |
| **Trends & Anomalies** | Statistical engine: climatology and z-score anomalies, annual means, OLS trend with autocorrelation-adjusted confidence intervals, seasonal Mann-Kendall with Sen's slope, Pettitt change-point test, early-vs-recent seasonal profile, year × month anomaly heatmap, missing-data accounting. |
| **AI Investigation** | *TerraTrend Intelligence* answers natural-language questions using only the statistics the engine computed, cites the dataset, and separates findings from hypotheses. Works with no API key (rule-based interpreter); optionally uses a Claude model if a key is provided. |
| **Regional Comparison** | Compare up to four regions on identical variables, paired tests on overlapping months, and automatic **opposite-trend detection** (e.g. one region warming significantly while another cools). |
| **Dataset Explorer** | Searches NASA's Common Metadata Repository for every collection intersecting the selected location, with provider, platform, instrument, temporal coverage, metadata and a granule check. |
| **Reports & Evidence** | One-click PDF, CSV, JSON and GeoJSON reports containing location geometry, datasets, coverage, statistics, anomalies, interpretation, methodology and limitations. A data-freshness panel shows the status of every source. |

## Scientific integrity

- Nothing is fabricated. If data or a key is missing the UI says *pending*, *not applicable* or *unavailable*.
- Every number is traceable: dataset, product ID, unit, grid resolution, observation period and method are shown beside each result.
- Trend significance accounts for autocorrelation (effective sample size for OLS; Hamed–Rao and Hirsch–Slack corrections for Mann-Kendall).
- Anomalies and trends are kept distinct; correlation is never presented as causation; reanalysis products are labelled as such.
- NASA POWER is a 0.5° × 0.625° gridded product. Small places use the grid cell at the centroid; larger regions are area-averaged across all cells, and this is stated on every chart.

## Data sources

| Source | Used for | Auth |
|---|---|---|
| [NASA POWER](https://power.larc.nasa.gov/) | Temperature, precipitation, humidity, wind, radiation, soil wetness (1981–present) | none |
| [NASA GIBS](https://gibs.earthdata.nasa.gov/) | Satellite imagery layers on the globe | none |
| [NASA EONET](https://eonet.gsfc.nasa.gov/) | Natural events | none |
| [NASA CMR](https://cmr.earthdata.nasa.gov/) | Dataset discovery | none |
| [USGS Earthquakes](https://earthquake.usgs.gov/) | Seismic events | none |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) | Active fire detections | free key (optional) |
| [OpenStreetMap Nominatim](https://nominatim.org/) | Geocoding and boundaries | none |

## Architecture

```
frontend/   CesiumJS globe · Plotly charts · vanilla JS (no build step)
backend/    FastAPI
  connectors/   one module per data source, cached, with retries and timeouts
  analysis/     NumPy / SciPy / pandas statistical engine
  services/     freshness registry · interpreter · PDF/CSV/GeoJSON report builder
```

API docs are auto-generated at `/docs` on the live site.

## Run locally

Requires Python 3.10+.

```bash
git clone https://github.com/sukruthasraoo/Terratrend-ai
cd Terratrend-ai
./run.sh          # Windows: run.bat
```
Open http://127.0.0.1:8000. No API keys are required. Optional keys go in `.env` (see `.env.example`).

Tests: `python tests/test_analysis.py`

## Deploy

`render.yaml` and `Dockerfile` are included. On Render: **New → Blueprint → pick this repo → Apply**.

## Known limitations

- Numeric time series for vegetation (MODIS NDVI), ocean (OISST) and cryosphere (ICESat-2, NSIDC) are not yet wired because those products need an Earthdata login; imagery and dataset discovery for them work today.
- First request for a large region over 25+ years can take 1–2 minutes (cached for 7 days afterwards).
- The free hosting tier sleeps after 15 minutes of inactivity; the first visit may take ~40 seconds.



