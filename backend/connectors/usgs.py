"""USGS Earthquake Hazards Program GeoJSON feeds and FDSN event query."""
from .. import cache
from ..http import fetch
from datetime import datetime, timezone

FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary"
QUERY = "https://earthquake.usgs.gov/fdsnws/event/1/query"

async def recent(window: str = "week", min_mag: str = "2.5"):
    key = {"w": window, "m": min_mag}
    c = cache.get("usgs", key)
    if c: return c
    data = await fetch(f"{FEED}/{min_mag}_{window}.geojson", timeout=60)
    out = _norm(data)
    return cache.put("usgs", key, out, ttl=600)

async def query(bbox, start: str, end: str, min_mag: float = 4.0, limit: int = 2000):
    w, s, e, n = bbox
    key = {"bbox": [round(v, 2) for v in bbox], "s": start, "e": end, "m": min_mag}
    c = cache.get("usgs_q", key)
    if c: return c
    data = await fetch(QUERY, {"format": "geojson", "starttime": start, "endtime": end, "minmagnitude": min_mag,
                              "minlongitude": w, "maxlongitude": e, "minlatitude": s, "maxlatitude": n,
                              "limit": limit, "orderby": "time"}, timeout=90)
    out = _norm(data)
    return cache.put("usgs_q", key, out, ttl=6 * 3600)

def _norm(data):
    out = []
    for f in data.get("features", []):
        p = f["properties"]; c = f["geometry"]["coordinates"]
        out.append({
            "id": f["id"], "title": p.get("title"), "category": "Earthquakes", "category_id": "earthquakes",
            "lat": c[1], "lon": c[0], "depth_km": c[2],
            "observed": datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc).isoformat() if p.get("time") else None,
            "published": datetime.fromtimestamp(p["updated"] / 1000, tz=timezone.utc).isoformat() if p.get("updated") else None,
            "magnitude": {"value": p.get("mag"), "unit": p.get("magType") or "M"},
            "quality": {"status": p.get("status"), "sig": p.get("sig"), "tsunami": p.get("tsunami"), "felt": p.get("felt")},
            "link": p.get("url"), "provider": "USGS Earthquake Hazards Program",
            "sources": [{"id": "USGS", "url": p.get("url")}],
        })
    return {"events": out, "generated": data.get("metadata", {}).get("generated"),
            "feed_title": data.get("metadata", {}).get("title")}