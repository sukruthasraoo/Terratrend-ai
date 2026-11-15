"""NASA FIRMS active fire detections (VIIRS/MODIS). Needs a free MAP_KEY."""
import csv, io
from .. import cache
from ..config import FIRMS_MAP_KEY
from ..http import fetch

BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

def available():
    return bool(FIRMS_MAP_KEY)

async def fires(bbox, days: int = 2, source: str = "VIIRS_SNPP_NRT"):
    if not FIRMS_MAP_KEY:
        return {"pending": True, "reason": "Set FIRMS_MAP_KEY in .env (free at firms.modaps.eosdis.nasa.gov/api/map_key/)", "events": []}
    w, s, e, n = bbox
    days = max(1, min(days, 10))
    key = {"bbox": [round(v, 2) for v in bbox], "days": days, "src": source}
    c = cache.get("firms", key)
    if c: return c
    url = f"{BASE}/{FIRMS_MAP_KEY}/{source}/{w:.3f},{s:.3f},{e:.3f},{n:.3f}/{days}"
    text = await fetch(url, as_json=False, timeout=90)
    rows = list(csv.DictReader(io.StringIO(text)))
    evs = []
    for r in rows[:5000]:
        evs.append({"id": f'firms-{r.get("latitude")}-{r.get("longitude")}-{r.get("acq_date")}{r.get("acq_time")}',
                    "title": f'Fire detection ({r.get("confidence")} confidence)', "category": "Wildfires", "category_id": "wildfires",
                    "lat": float(r["latitude"]), "lon": float(r["longitude"]),
                    "observed": f'{r.get("acq_date")}T{str(r.get("acq_time","0000")).zfill(4)[:2]}:{str(r.get("acq_time","0000")).zfill(4)[2:]}:00Z',
                    "magnitude": {"value": _f(r.get("frp")), "unit": "MW (fire radiative power)"},
                    "quality": {"confidence": r.get("confidence"), "daynight": r.get("daynight")},
                    "sensor": f'{r.get("satellite")} / {r.get("instrument")}', "provider": "NASA FIRMS",
                    "sources": [{"id": "FIRMS", "url": "https://firms.modaps.eosdis.nasa.gov/"}]})
    out = {"pending": False, "events": evs, "count": len(rows), "source": source, "days": days}
    return cache.put("firms", key, out, ttl=1800)

def _f(x):
    try: return float(x)
    except Exception: return None