"""Location resolution via OpenStreetMap Nominatim (geocoding, reverse geocoding,
administrative boundary polygons). No key needed; we respect the usage policy by
caching aggressively and sending a proper User-Agent."""
from .. import cache
from ..http import fetch

NOMINATIM = "https://nominatim.openstreetmap.org"

def _place_type(item):
    t = (item.get("addresstype") or item.get("type") or "").lower()
    cls = item.get("class", "")
    if t in ("country",): return "country"
    if t in ("state", "province", "region", "county"): return "state"
    if t in ("city", "town", "village", "municipality", "suburb"): return "city"
    if cls == "natural" or t in ("ocean", "sea", "desert", "mountain_range", "peninsula", "bay", "forest"): return "natural"
    return "region"

async def search(q: str, limit: int = 6):
    cached = cache.get("geocode", {"q": q, "limit": limit})
    if cached: return cached
    data = await fetch(f"{NOMINATIM}/search", {
        "q": q, "format": "jsonv2", "limit": limit, "polygon_geojson": 1,
        "addressdetails": 1, "polygon_threshold": 0.005})
    out = []
    for it in data:
        geom = it.get("geojson")
        bb = [float(it["boundingbox"][2]), float(it["boundingbox"][0]), float(it["boundingbox"][3]), float(it["boundingbox"][1])]
        out.append({
            "name": it.get("display_name"),
            "short_name": it.get("name") or it.get("display_name", "").split(",")[0],
            "type": _place_type(it),
            "osm_id": f'{it.get("osm_type","")}{it.get("osm_id","")}',
            "lat": float(it["lat"]), "lon": float(it["lon"]),
            "bbox": bb,
            "geometry": geom if geom and geom.get("type") in ("Polygon", "MultiPolygon") else None,
            "country": (it.get("address") or {}).get("country"),
        })
    return cache.put("geocode", {"q": q, "limit": limit}, out, ttl=30 * 86400)

async def reverse(lat: float, lon: float):
    cached = cache.get("revgeo", {"lat": round(lat, 3), "lon": round(lon, 3)})
    if cached: return cached
    try:
        it = await fetch(f"{NOMINATIM}/reverse", {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 10})
        name = it.get("display_name") or f"{lat:.3f}, {lon:.3f}"
    except Exception:
        name = f"{lat:.3f}, {lon:.3f}"
    out = {"name": name, "short_name": name.split(",")[0], "type": "point", "lat": lat, "lon": lon,
           "bbox": [lon - 0.25, lat - 0.25, lon + 0.25, lat + 0.25], "geometry": None}
    return cache.put("revgeo", {"lat": round(lat, 3), "lon": round(lon, 3)}, out, ttl=30 * 86400)

def context_from_place(place: dict) -> dict:
    """Standardised investigation context shared by every module."""
    bb = place["bbox"]
    area_deg2 = max(0.0, (bb[2] - bb[0]) * (bb[3] - bb[1]))
    return {
        "name": place["name"], "short_name": place.get("short_name"), "type": place.get("type", "region"),
        "lat": place["lat"], "lon": place["lon"], "bbox": bb,
        "geometry": place.get("geometry"), "country": place.get("country"),
        "approx_area_deg2": round(area_deg2, 4),
        "aggregation": "polygon" if place.get("geometry") else "bbox",
        "notes": "NASA POWER values are for the ~0.5°×0.625° grid cell(s) covering this area, "
                 "not a single station; large regions are area-averaged over the bounding box.",
    }
