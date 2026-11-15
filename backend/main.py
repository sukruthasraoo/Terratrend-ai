"""TerraTrend AI — FastAPI backend and static frontend host.
Run:  uvicorn backend.main:app --reload   (or ./run.sh / run.bat)"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .connectors import geocode, power, eonet, usgs, firms, cmr, gibs
from .analysis import stats
from .services import freshness, ai, reports

app = FastAPI(title="TerraTrend AI", version="0.1.0",
              description="Global Earth intelligence & environmental investigation platform")

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(FRONTEND / "index.html")


# ───────────────────────── schemas ─────────────────────────
class Place(BaseModel):
    name: str
    short_name: Optional[str] = None
    type: str = "region"
    lat: float
    lon: float
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    geometry: Optional[dict] = None
    country: Optional[str] = None


class Investigation(BaseModel):
    place: Place
    category: str = "climate"
    variables: Optional[list[str]] = None
    start_year: int = 1995
    end_year: Optional[int] = None
    baseline: Optional[list[int]] = None   # e.g. [1991, 2020]


class Comparison(BaseModel):
    places: list[Place] = Field(..., min_length=2, max_length=4)
    variables: list[str] = ["T2M", "PRECTOTCORR"]
    start_year: int = 1995
    end_year: Optional[int] = None


class AIRequest(BaseModel):
    question: str
    investigation: Investigation


class ReportRequest(BaseModel):
    investigation: Investigation
    question: Optional[str] = "Summarise the environmental changes at this location."
    title: Optional[str] = None
    include_ai: bool = True


# ───────────────────────── system ─────────────────────────
@app.get("/api/health")
async def health():
    return {"ok": True, "time": datetime.now(timezone.utc).isoformat(), "version": app.version,
            "features": {"firms": firms.available(), "ai": bool(config.ANTHROPIC_API_KEY), "cesium_ion": bool(config.CESIUM_ION_TOKEN)}}


@app.get("/api/system/data-freshness")
async def data_freshness():
    return freshness.status()


@app.get("/api/system/config")
async def public_config():
    """Only non-secret config reaches the browser. The Cesium ion token is a browser
    token by design (scoped, non-secret); all other keys stay server-side."""
    return {"cesium_ion_token": config.CESIUM_ION_TOKEN, "ai_enabled": bool(config.ANTHROPIC_API_KEY), "firms_enabled": firms.available()}


# ───────────────────────── locations ─────────────────────────
@app.get("/api/locations/search")
async def locations_search(q: str = Query(..., min_length=2), limit: int = 6):
    try:
        res = await geocode.search(q, limit)
        freshness.record("osm_nominatim", True)
        return {"results": res}
    except Exception as e:
        freshness.record("osm_nominatim", False, error=str(e))
        raise HTTPException(502, f"Geocoder unavailable: {e}")


@app.get("/api/locations/resolve")
async def locations_resolve(lat: float, lon: float):
    p = await geocode.reverse(lat, lon)
    return {"place": p, "context": geocode.context_from_place(p)}


# ───────────────────────── imagery layers ─────────────────────────
@app.get("/api/layers")
async def layers():
    return {"gibs": gibs.catalogue(), "note": "Tiles are requested by the browser directly from NASA GIBS WMTS (EPSG:4326)."}


# ───────────────────────── events ─────────────────────────
@app.get("/api/events")
async def events(days: int = 30, status: str = "open", category: Optional[str] = None,
                 bbox: Optional[str] = None, include_quakes: bool = True, min_mag: str = "2.5", fires_days: int = 2):
    bb = [float(x) for x in bbox.split(",")] if bbox else None
    out = {"events": [], "sources": [], "generated": datetime.now(timezone.utc).isoformat()}

    async def _eonet():
        try:
            ev = await eonet.events(days, status, category, bb)
            freshness.record("nasa_eonet", True, max((e["observed"] or "" for e in ev), default=None))
            out["events"] += ev; out["sources"].append({"id": "nasa_eonet", "ok": True, "count": len(ev)})
        except Exception as e:
            freshness.record("nasa_eonet", False, error=str(e)); out["sources"].append({"id": "nasa_eonet", "ok": False, "error": str(e)[:200]})

    async def _usgs():
        if not include_quakes: return
        try:
            if bb:
                end = datetime.now(timezone.utc); start = end - timedelta(days=min(days, 365))
                r = await usgs.query(bb, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), float(min_mag))
            else:
                r = await usgs.recent("week" if days <= 7 else "month", min_mag)
            ev = r["events"]
            freshness.record("usgs_eq", True, max((e["observed"] or "" for e in ev), default=None))
            out["events"] += ev; out["sources"].append({"id": "usgs_eq", "ok": True, "count": len(ev), "feed": r.get("feed_title")})
        except Exception as e:
            freshness.record("usgs_eq", False, error=str(e)); out["sources"].append({"id": "usgs_eq", "ok": False, "error": str(e)[:200]})

    async def _firms():
        if not bb:
            out["sources"].append({"id": "nasa_firms", "ok": False, "pending": True, "error": "FIRMS requires a bounding box (select a location)"}); return
        try:
            r = await firms.fires(bb, fires_days)
            if r.get("pending"):
                out["sources"].append({"id": "nasa_firms", "ok": False, "pending": True, "error": r["reason"]}); return
            freshness.record("nasa_firms", True, max((e["observed"] for e in r["events"]), default=None))
            out["events"] += r["events"]; out["sources"].append({"id": "nasa_firms", "ok": True, "count": r["count"]})
        except Exception as e:
            freshness.record("nasa_firms", False, error=str(e)); out["sources"].append({"id": "nasa_firms", "ok": False, "error": str(e)[:200]})

    await asyncio.gather(_eonet(), _usgs(), _firms())
    out["events"].sort(key=lambda e: e.get("observed") or "", reverse=True)
    return out


@app.get("/api/events/categories")
async def event_categories():
    cats = await eonet.categories()
    return {"categories": cats + [{"id": "earthquakes", "title": "Earthquakes"}]}


# ───────────────────────── datasets ─────────────────────────
@app.get("/api/datasets/search")
async def datasets_search(bbox: str, q: str = "", category: Optional[str] = None, temporal: Optional[str] = None,
                          page: int = 1, page_size: int = 20, provider: Optional[str] = None):
    bb = [float(x) for x in bbox.split(",")]
    kw = q or (cmr.CATEGORY_KEYWORDS.get(category, "") if category else "")
    try:
        r = await cmr.collections(bb, kw, temporal, page_size, page, provider)
        freshness.record("nasa_cmr", True)
        return r
    except Exception as e:
        freshness.record("nasa_cmr", False, error=str(e))
        raise HTTPException(502, f"CMR unavailable: {e}")


@app.get("/api/datasets/availability")
async def datasets_availability(bbox: str, place_type: str = "region"):
    """Which of the nine categories have a working numeric connector here, plus CMR hits."""
    bb = [float(x) for x in bbox.split(",")]
    w, s, e, n = bb
    is_land_guess = place_type in ("city", "state", "country")
    cats = {
        "climate": {"status": "available", "connector": "NASA POWER", "variables": power.CATEGORY_VARS["climate"]},
        "atmosphere": {"status": "partial", "connector": "NASA POWER (humidity only) + GIBS aerosol imagery", "variables": power.CATEGORY_VARS["atmosphere"]},
        "vegetation": {"status": "imagery", "connector": "GIBS MODIS NDVI imagery; numeric NDVI series pending (LP DAAC AppEEARS needs Earthdata login)", "variables": []},
        "ocean": {"status": "imagery" if not is_land_guess else "not applicable", "connector": "GIBS MUR SST imagery; OISST series connector pending", "variables": []},
        "water": {"status": "available", "connector": "NASA POWER (precipitation, soil wetness)", "variables": power.CATEGORY_VARS["water"]},
        "cryosphere": {"status": "imagery" if (n > 45 or s < -45) else "not applicable", "connector": "GIBS snow/sea-ice imagery; ICESat-2/NSIDC series pending", "variables": []},
        "hazards": {"status": "available", "connector": "EONET + USGS" + (" + FIRMS" if firms.available() else " (FIRMS pending key)"), "variables": []},
        "land": {"status": "partial", "connector": "NASA POWER skin temperature + GIBS LST imagery", "variables": power.CATEGORY_VARS["land"]},
        "energy": {"status": "available", "connector": "NASA POWER (CERES-derived radiation)", "variables": power.CATEGORY_VARS["energy"]},
    }
    async def _hits(cat):
        try:
            r = await cmr.collections(bb, cmr.CATEGORY_KEYWORDS[cat], None, 3, 1)
            cats[cat]["cmr_hits"] = r["hits"]; cats[cat]["cmr_examples"] = [{"title": i["title"], "id": i["id"]} for i in r["items"][:3]]
        except Exception as ex:
            cats[cat]["cmr_hits"] = None; cats[cat]["cmr_error"] = str(ex)[:120]
    await asyncio.gather(*[_hits(c) for c in cats])
    return {"bbox": bb, "categories": cats}


@app.get("/api/datasets/{dataset_id}")
async def dataset_detail(dataset_id: str, bbox: Optional[str] = None):
    c = await cmr.collection(dataset_id)
    if not c: raise HTTPException(404, "Collection not found in CMR")
    gran = None
    if bbox:
        gran = await cmr.granule_count(dataset_id, [float(x) for x in bbox.split(",")])
    return {"collection": c, "granules_in_bbox_sample": gran}


# ───────────────────────── environment / investigation ─────────────────────────
async def run_investigation(inv: Investigation) -> dict:
    p = inv.place.model_dump()
    ctx = geocode.context_from_place(p)
    end_year = inv.end_year or datetime.now(timezone.utc).year
    cat = inv.category if inv.category in power.CATEGORY_VARS else "climate"
    vars_ = [v for v in (inv.variables or power.CATEGORY_VARS[cat]) if v in power.VARIABLES]
    if not vars_: raise HTTPException(400, "No supported variables requested")
    big = ctx["approx_area_deg2"] > 1.0
    try:
        if big:
            raw = await power.monthly_regional(p["bbox"], inv.start_year, end_year, vars_)
        else:
            raw = await power.monthly(p["lat"], p["lon"], inv.start_year, end_year, vars_)
        freshness.record("nasa_power", True, max((pt["t"] for s in raw["series"].values() for pt in s), default=None))
    except Exception as e:
        freshness.record("nasa_power", False, error=str(e))
        raise HTTPException(502, f"NASA POWER unavailable: {e}")
    bs, be = (inv.baseline or [None, None])[:2]
    variables = {}
    for v in vars_:
        meta = power.VARIABLES[v]
        r = await asyncio.to_thread(stats.analyse_variable, raw["series"][v], meta["unit"], meta["label"], bs, be)
        r["product_kind"] = meta["kind"]; r["product_id"] = f"NASA POWER {v}"
        variables[v] = r
    return {"context": ctx, "category": cat, "period": [inv.start_year, end_year], "aggregation": raw["aggregation"],
            "n_cells": raw.get("n_cells"), "sources": [f"{raw['source']} — https://power.larc.nasa.gov/ (parameters {', '.join(vars_)})"],
            "variables": variables, "retrieved": datetime.now(timezone.utc).isoformat(),
            "provenance": {"provider": "NASA Langley Research Center POWER project", "upstream": "MERRA-2 / GEOS-IT reanalysis; CERES SYN1deg & FLASHFlux radiation",
                           "grid": "0.5° lat × 0.625° lon", "temporal": "monthly means", "access": "https://power.larc.nasa.gov/api/temporal/monthly/"}}


@app.post("/api/investigation")
async def investigation(inv: Investigation):
    return await run_investigation(inv)


for _cat in ("overview", "climate", "atmosphere", "vegetation", "ocean", "water", "cryosphere", "hazards", "land", "energy"):
    def _mk(cat):
        async def _ep(lat: float, lon: float, bbox: Optional[str] = None, name: str = "", start_year: int = 1995, end_year: Optional[int] = None):
            bb = [float(x) for x in bbox.split(",")] if bbox else [lon - 0.25, lat - 0.25, lon + 0.25, lat + 0.25]
            pl = Place(name=name or f"{lat:.3f}, {lon:.3f}", lat=lat, lon=lon, bbox=bb)
            if cat in power.CATEGORY_VARS:
                return await run_investigation(Investigation(place=pl, category=cat, start_year=start_year, end_year=end_year))
            if cat == "hazards":
                return await events(days=365, status="all", bbox=",".join(map(str, bb)))
            av = await datasets_availability(",".join(map(str, bb)))
            return {"category": cat, "status": av["categories"].get(cat, {}), "note": "Numeric series connector pending for this category; imagery available on the globe via GIBS."}
        _ep.__name__ = f"environment_{cat}"
        return _ep
    app.get(f"/api/environment/{_cat}", name=f"environment_{_cat}")(_mk(_cat))


@app.get("/api/trends")
async def trends(lat: float, lon: float, variable: str = "T2M", start_year: int = 1981, end_year: Optional[int] = None, bbox: Optional[str] = None):
    bb = [float(x) for x in bbox.split(",")] if bbox else [lon - 0.25, lat - 0.25, lon + 0.25, lat + 0.25]
    r = await run_investigation(Investigation(place=Place(name=f"{lat:.3f}, {lon:.3f}", lat=lat, lon=lon, bbox=bb), variables=[variable], start_year=start_year, end_year=end_year))
    v = r["variables"][variable]
    return {k: v.get(k) for k in ("label", "unit", "coverage", "annual", "trend_ols", "trend_mk_seasonal", "trend_mk_annual", "change_point", "seasonal")}


@app.get("/api/anomalies")
async def anomalies_ep(lat: float, lon: float, variable: str = "T2M", start_year: int = 1981, end_year: Optional[int] = None, bbox: Optional[str] = None):
    bb = [float(x) for x in bbox.split(",")] if bbox else [lon - 0.25, lat - 0.25, lon + 0.25, lat + 0.25]
    r = await run_investigation(Investigation(place=Place(name=f"{lat:.3f}, {lon:.3f}", lat=lat, lon=lon, bbox=bb), variables=[variable], start_year=start_year, end_year=end_year))
    v = r["variables"][variable]
    return {"label": v["label"], "unit": v["unit"], "climatology": v["climatology"], "anomalies": v["anomalies"]}


@app.post("/api/comparison")
async def comparison(cmp: Comparison):
    results = await asyncio.gather(*[run_investigation(Investigation(place=p, variables=cmp.variables, start_year=cmp.start_year, end_year=cmp.end_year)) for p in cmp.places])
    pairs = []
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            for v in cmp.variables:
                c = await asyncio.to_thread(stats.compare, results[i]["variables"].get(v, {}), results[j]["variables"].get(v, {}))
                pairs.append({"a": cmp.places[i].name, "b": cmp.places[j].name, "variable": v, **c})
    opposite = [p for p in pairs if p.get("opposite_trends")]
    return {"regions": results, "pairs": pairs, "opposite_trends": opposite,
            "note": "Comparisons use identical POWER variable definitions and overlapping months only."}


@app.post("/api/ai/interpret")
async def ai_interpret(req: AIRequest):
    res = await run_investigation(req.investigation)
    out = await ai.interpret(req.question, res["context"], res)
    freshness.record("ai", True)
    return {**out, "evidence": {v: {"trend_ols": r.get("trend_ols"), "trend_mk_seasonal": r.get("trend_mk_seasonal"), "coverage": r.get("coverage")}
                                for v, r in res["variables"].items()}, "sources": res["sources"], "period": res["period"]}


@app.post("/api/reports/generate")
async def report_generate(req: ReportRequest):
    res = await run_investigation(req.investigation)
    ai_text = None
    if req.include_ai:
        ai_text = (await ai.interpret(req.question or "Summarise the findings.", res["context"], res))["answer"]
    return await asyncio.to_thread(reports.build, res["context"], res, ai_text, req.title)


@app.get("/api/reports/{report_id}")
async def report_meta(report_id: str):
    p = config.REPORTS_DIR / f"{report_id}.json"
    if not p.exists(): raise HTTPException(404, "Report not found")
    return {"report_id": report_id, "files": {fmt: f"/api/reports/{report_id}/{fmt}" for fmt in ("json", "csv", "geojson", "pdf")}}


@app.get("/api/reports/{report_id}/{fmt}")
async def report_file(report_id: str, fmt: str):
    if fmt not in ("json", "csv", "geojson", "pdf"): raise HTTPException(400, "Unsupported format")
    p = config.REPORTS_DIR / f"{report_id}.{fmt}"
    if not p.exists(): raise HTTPException(404, "File not found")
    media = {"json": "application/json", "csv": "text/csv", "geojson": "application/geo+json", "pdf": "application/pdf"}[fmt]
    return FileResponse(p, media_type=media, filename=f"terratrend-{report_id}.{fmt}")