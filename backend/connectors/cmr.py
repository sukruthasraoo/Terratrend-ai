"""NASA Common Metadata Repository — dataset discovery by location/time/keyword."""
from .. import cache
from ..http import fetch

BASE = "https://cmr.earthdata.nasa.gov/search"

CATEGORY_KEYWORDS = {
    "climate": "temperature precipitation reanalysis",
    "atmosphere": "aerosol optical depth",
    "vegetation": "NDVI vegetation index",
    "ocean": "sea surface temperature chlorophyll",
    "water": "soil moisture precipitation terrestrial water storage",
    "cryosphere": "snow cover ice elevation sea ice",
    "hazards": "active fire",
    "land": "land surface temperature land cover",
    "energy": "radiation budget CERES",
}

async def collections(bbox, keyword: str = "", temporal: str | None = None, page_size: int = 25, page: int = 1, provider: str | None = None):
    w, s, e, n = bbox
    key = {"bbox": [round(v, 2) for v in bbox], "k": keyword, "t": temporal, "ps": page_size, "p": page, "pr": provider}
    c = cache.get("cmr", key)
    if c: return c
    params = {"bounding_box": f"{w:.4f},{s:.4f},{e:.4f},{n:.4f}", "page_size": page_size, "page_num": page,
              "sort_key": "-usage_score", "has_granules": "true"}
    if keyword: params["keyword"] = keyword
    if temporal: params["temporal"] = temporal
    if provider: params["provider"] = provider
    data, hdrs = await fetch(f"{BASE}/collections.json", params, timeout=60, with_headers=True)
    items = []
    for e_ in data.get("feed", {}).get("entry", []):
        items.append({
            "id": e_.get("id"), "short_name": e_.get("short_name"), "version": e_.get("version_id"),
            "title": e_.get("title"), "provider": e_.get("data_center"), "processing_level": e_.get("processing_level_id"),
            "summary": (e_.get("summary") or "")[:600], "time_start": e_.get("time_start"), "time_end": e_.get("time_end"),
            "platforms": [p.get("short_name") for p in e_.get("platforms", []) if isinstance(p, dict)],
            "instruments": [i.get("short_name") for p in e_.get("platforms", []) if isinstance(p, dict) for i in p.get("instruments", [])],
            "online_access": e_.get("online_access_flag"), "cloud_hosted": e_.get("cloud_hosted"),
            "links": [{"href": l.get("href"), "rel": l.get("rel", "").split("/")[-1][:40]} for l in e_.get("links", []) if l.get("href", "").startswith("http")][:8],
            "boxes": e_.get("boxes"), "updated": e_.get("updated"),
        })
    out = {"items": items, "hits": int(hdrs.get("cmr-hits", len(items)) or 0), "page": page, "page_size": page_size}
    return cache.put("cmr", key, out, ttl=86400)

async def collection(concept_id: str):
    c = cache.get("cmr_one", {"id": concept_id})
    if c: return c
    data = await fetch(f"{BASE}/collections.json", {"concept_id": concept_id})
    ent = data.get("feed", {}).get("entry", [])
    out = ent[0] if ent else None
    return cache.put("cmr_one", {"id": concept_id}, out, ttl=86400)

async def granule_count(concept_id: str, bbox, temporal: str | None = None):
    w, s, e, n = bbox
    params = {"collection_concept_id": concept_id, "bounding_box": f"{w:.4f},{s:.4f},{e:.4f},{n:.4f}", "page_size": 1}
    if temporal: params["temporal"] = temporal
    try:
        data = await fetch(f"{BASE}/granules.json", params, timeout=45)
        return len(data.get("feed", {}).get("entry", []))
    except Exception:
        return None