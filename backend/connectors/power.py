"""NASA POWER (Prediction Of Worldwide Energy Resources) climatology/meteorology.
Docs: https://power.larc.nasa.gov/docs/services/api/
Source: MERRA-2 / GEOS reanalysis + CERES/FLASHFlux radiation. Gridded 0.5°×0.625°."""
import asyncio
from .. import cache
from ..http import fetch

BASE = "https://power.larc.nasa.gov/api/temporal"
VARIABLES = {
    "T2M": {"label": "Mean temperature (2 m)", "unit": "°C", "kind": "reanalysis"},
    "T2M_MAX": {"label": "Maximum temperature (2 m)", "unit": "°C", "kind": "reanalysis"},
    "T2M_MIN": {"label": "Minimum temperature (2 m)", "unit": "°C", "kind": "reanalysis"},
    "PRECTOTCORR": {"label": "Precipitation (bias-corrected)", "unit": "mm/day", "kind": "reanalysis"},
    "RH2M": {"label": "Relative humidity (2 m)", "unit": "%", "kind": "reanalysis"},
    "WS2M": {"label": "Wind speed (2 m)", "unit": "m/s", "kind": "reanalysis"},
    "ALLSKY_SFC_SW_DWN": {"label": "All-sky surface shortwave down", "unit": "MJ/m²/day", "kind": "satellite-derived"},
    "CLRSKY_SFC_SW_DWN": {"label": "Clear-sky surface shortwave down", "unit": "MJ/m²/day", "kind": "satellite-derived"},
    "ALLSKY_SFC_LW_DWN": {"label": "All-sky surface longwave down", "unit": "MJ/m²/day", "kind": "satellite-derived"},
    "GWETROOT": {"label": "Root-zone soil wetness", "unit": "fraction", "kind": "reanalysis"},
    "GWETTOP": {"label": "Surface soil wetness", "unit": "fraction", "kind": "reanalysis"},
    "TS": {"label": "Earth skin temperature", "unit": "°C", "kind": "reanalysis"},
    "QV2M": {"label": "Specific humidity (2 m)", "unit": "g/kg", "kind": "reanalysis"},
}
CATEGORY_VARS = {
    "climate": ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN"],
    "water": ["PRECTOTCORR", "GWETROOT", "GWETTOP"],
    "energy": ["ALLSKY_SFC_SW_DWN", "CLRSKY_SFC_SW_DWN", "ALLSKY_SFC_LW_DWN"],
    "land": ["TS", "T2M_MAX"],
    "atmosphere": ["QV2M", "RH2M"],
}

async def monthly(lat: float, lon: float, start_year: int, end_year: int, params: list[str], community="AG"):
    key = {"lat": round(lat, 3), "lon": round(lon, 3), "s": start_year, "e": end_year, "p": sorted(params)}
    c = cache.get("power_monthly", key)
    if c: return c
    data = await fetch(f"{BASE}/monthly/point", {
        "parameters": ",".join(params), "community": community, "longitude": lon, "latitude": lat,
        "start": start_year, "end": end_year, "format": "JSON"}, timeout=60)
    out = _normalise(data, params)
    return cache.put("power_monthly", key, out, ttl=7 * 86400)

async def monthly_regional(bbox, start_year, end_year, params, community="AG"):
    """Regional request (area average over POWER grid cells). The regional endpoint
    accepts ONE parameter per call and boxes up to 10°×10° (min 2°×2°), so we clamp the
    box and fetch parameters concurrently."""
    w, s, e, n = bbox
    cx, cy = (w + e) / 2, (s + n) / 2
    w, e = max(w, cx - 5), min(e, cx + 5)
    s, n = max(s, cy - 5), min(n, cy + 5)
    if e - w < 2: w, e = cx - 1, cx + 1
    if n - s < 2: s, n = cy - 1, cy + 1
    box = [round(v, 2) for v in (w, s, e, n)]

    async def one(p):
        key = {"bbox": box, "s": start_year, "e": end_year, "p": p}
        c = cache.get("power_regional", key)
        if c: return p, c
        data = await fetch(f"{BASE}/monthly/regional", {
            "parameters": p, "community": community,
            "longitude-min": w, "longitude-max": e, "latitude-min": s, "latitude-max": n,
            "start": start_year, "end": end_year, "format": "JSON"}, timeout=180)
        agg: dict[str, list] = {}
        feats = data.get("features", [])
        for f in feats:
            for k, v in f.get("properties", {}).get("parameter", {}).get(p, {}).items():
                if v is not None and v > -900:
                    agg.setdefault(k, []).append(v)
        pts = [{"t": f"{k[:4]}-{k[4:]}", "v": sum(vals) / len(vals)} for k, vals in sorted(agg.items()) if len(k) == 6 and k[4:] != "13"]
        return p, cache.put("power_regional", key, {"pts": pts, "n": len(feats)}, ttl=7 * 86400)

    res = dict(await asyncio.gather(*[one(p) for p in params]))
    n_cells = max((r["n"] for r in res.values()), default=0)
    return {"series": {p: res[p]["pts"] for p in params}, "n_cells": n_cells,
            "aggregation": f"area mean of {n_cells} POWER grid cells (0.5°×0.625°) over bbox {box}; box clamped to 10°×10° max",
            "bbox_used": box, "source": "NASA POWER monthly regional", "units": {p: VARIABLES[p]["unit"] for p in params}}

def _normalise(data, params):
    pr = data.get("properties", {}).get("parameter", {})
    series = {}
    for p in params:
        pts = []
        for k, v in sorted(pr.get(p, {}).items()):
            if len(k) == 6 and k[4:] != "13" and v is not None and v > -900:  # "13" = annual mean; -999 = fill
                pts.append({"t": f"{k[:4]}-{k[4:]}", "v": v})
        series[p] = pts
    hdr = data.get("header", {})
    return {"series": series, "n_cells": 1, "aggregation": "single POWER grid cell (0.5°×0.625°) containing the centroid",
            "source": "NASA POWER monthly point", "fill_value": hdr.get("fill_value"),
            "units": {p: VARIABLES[p]["unit"] for p in params},
            "api_version": hdr.get("api", {}).get("version"), "retrieved": hdr.get("api", {}).get("name")}