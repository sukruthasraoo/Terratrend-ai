"""Central data-freshness registry. Each connector reports its latest successful
retrieval and observation timestamps; the UI shows an honest status per source."""
import time
from datetime import datetime, timezone
from ..config import FIRMS_MAP_KEY, ANTHROPIC_API_KEY
from ..http import recent_errors

_reg: dict[str, dict] = {}

SOURCES = {
    "nasa_power":  {"name": "NASA POWER", "product": "Monthly point/regional (MERRA-2, CERES)", "cadence": "monthly; ~1–2 month latency", "auth": "none"},
    "nasa_eonet":  {"name": "NASA EONET v3", "product": "Curated natural events", "cadence": "irregular; minutes–days", "auth": "none"},
    "usgs_eq":     {"name": "USGS Earthquakes", "product": "GeoJSON feeds / FDSN", "cadence": "every ~minute", "auth": "none"},
    "nasa_firms":  {"name": "NASA FIRMS", "product": "VIIRS/MODIS active fires", "cadence": "≤3 h (NRT)", "auth": "MAP_KEY"},
    "nasa_gibs":   {"name": "NASA GIBS", "product": "WMTS imagery tiles", "cadence": "daily (3–5 h NRT for some)", "auth": "none"},
    "nasa_cmr":    {"name": "NASA CMR", "product": "Collection/granule metadata", "cadence": "continuous", "auth": "none"},
    "osm_nominatim": {"name": "OSM Nominatim", "product": "Geocoding & boundaries", "cadence": "n/a", "auth": "none"},
    "ai":          {"name": "TerraTrend Intelligence", "product": "Interpretation", "cadence": "on demand", "auth": "ANTHROPIC_API_KEY (optional)"},
    "modis_lp":    {"name": "MODIS/VIIRS via LP DAAC", "product": "NDVI/LST time series", "cadence": "8–16 day", "auth": "Earthdata login"},
    "grace_fo":    {"name": "GRACE-FO", "product": "Terrestrial water storage", "cadence": "monthly", "auth": "Earthdata login"},
    "smap":        {"name": "SMAP", "product": "Soil moisture", "cadence": "2–3 day", "auth": "Earthdata login"},
    "icesat2":     {"name": "ICESat-2", "product": "Ice/land elevation", "cadence": "91-day repeat", "auth": "Earthdata login"},
    "oisst":       {"name": "NOAA OISST", "product": "Sea surface temperature", "cadence": "daily", "auth": "none (file download)"},
    "ocean_color": {"name": "NASA Ocean Color", "product": "Chlorophyll", "cadence": "daily/8-day", "auth": "Earthdata login"},
    "ceres":       {"name": "NASA CERES", "product": "Radiation budget", "cadence": "monthly", "auth": "none / Earthdata"},
}

def record(source: str, ok: bool, latest_observation: str | None = None, error: str | None = None):
    _reg[source] = {"last_attempt": time.time(), "ok": ok, "latest_observation": latest_observation,
                    "error": error, "last_success": time.time() if ok else _reg.get(source, {}).get("last_success")}

def status():
    now = time.time(); out = []
    for k, meta in SOURCES.items():
        r = _reg.get(k, {})
        if k == "nasa_firms" and not FIRMS_MAP_KEY: st = "pending: needs FIRMS_MAP_KEY"
        elif k == "ai": st = "Claude model connected" if ANTHROPIC_API_KEY else "rule-based interpreter (no API key)"
        elif k in ("modis_lp", "grace_fo", "smap", "icesat2", "oisst", "ocean_color", "ceres"):
            st = "imagery via GIBS only; numeric time-series connector pending (needs Earthdata login / large-file access)"
        elif not r: st = "not yet queried"
        elif r["ok"]: st = "recently updated" if now - r["last_success"] < 3600 else "historical / cached"
        else: st = "temporarily unavailable"
        out.append({"id": k, **meta, "status": st,
                    "last_success": datetime.fromtimestamp(r["last_success"], tz=timezone.utc).isoformat() if r.get("last_success") else None,
                    "latest_observation": r.get("latest_observation"), "error": r.get("error")})
    return {"generated": datetime.now(timezone.utc).isoformat(), "sources": out, "recent_errors": recent_errors(20)}