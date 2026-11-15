"""NASA EONET v3 — curated natural events (wildfires, storms, volcanoes, ice, floods...)."""
from .. import cache
from ..http import fetch

BASE = "https://eonet.gsfc.nasa.gov/api/v3"

async def events(days: int = 30, status: str = "open", category: str | None = None, bbox=None):
    key = {"days": days, "status": status, "category": category, "bbox": bbox}
    c = cache.get("eonet", key)
    if c: return c
    params = {"days": days, "status": status}
    if category: params["category"] = category
    if bbox:
        w, s, e, n = bbox
        params["bbox"] = f"{w},{n},{e},{s}"   # EONET wants minLon,maxLat,maxLon,minLat
    data = await fetch(f"{BASE}/events", params, timeout=60)
    out = []
    for ev in data.get("events", []):
        geos = ev.get("geometry", [])
        if not geos: continue
        last = geos[-1]
        coords = last.get("coordinates")
        if last.get("type") == "Polygon":
            ring = coords[0]; lon = sum(p[0] for p in ring) / len(ring); lat = sum(p[1] for p in ring) / len(ring)
        else:
            lon, lat = coords[0], coords[1]
        out.append({
            "id": ev["id"], "title": ev["title"], "category": (ev.get("categories") or [{}])[0].get("title", "Other"),
            "category_id": (ev.get("categories") or [{}])[0].get("id"),
            "lat": lat, "lon": lon, "observed": last.get("date"), "n_observations": len(geos),
            "magnitude": {"value": last.get("magnitudeValue"), "unit": last.get("magnitudeUnit")},
            "sources": [{"id": s.get("id"), "url": s.get("url")} for s in ev.get("sources", [])],
            "closed": ev.get("closed"), "link": ev.get("link"),
            "provider": "NASA EONET v3", "track": [{"t": g.get("date"), "lon": (g["coordinates"][0] if g["type"]=="Point" else None),
                                                   "lat": (g["coordinates"][1] if g["type"]=="Point" else None)} for g in geos][-30:],
        })
    return cache.put("eonet", key, out, ttl=1800)

async def categories():
    c = cache.get("eonet_cats", {})
    if c: return c
    data = await fetch(f"{BASE}/categories")
    out = [{"id": x["id"], "title": x["title"]} for x in data.get("categories", [])]
    return cache.put("eonet_cats", {}, out, ttl=86400)