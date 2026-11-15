"""Two-tier cache (memory + JSON files on disk) with per-key TTL.
Keeps us from hammering NASA/NOAA/USGS endpoints for the same request."""
import hashlib, json, time
from pathlib import Path
from typing import Any, Optional
from .config import CACHE_DIR

_mem: dict[str, tuple[float, Any]] = {}

def _key(ns: str, params: Any) -> str:
    raw = ns + "|" + json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()

def get(ns: str, params: Any) -> Optional[Any]:
    k = _key(ns, params)
    hit = _mem.get(k)
    if hit and hit[0] > time.time():
        return hit[1]
    p: Path = CACHE_DIR / f"{k}.json"
    if p.exists():
        try:
            d = json.loads(p.read_text())
            if d["expires"] > time.time():
                _mem[k] = (d["expires"], d["value"])
                return d["value"]
            p.unlink(missing_ok=True)
        except Exception:
            p.unlink(missing_ok=True)
    return None

def put(ns: str, params: Any, value: Any, ttl: int) -> Any:
    k = _key(ns, params)
    exp = time.time() + ttl
    _mem[k] = (exp, value)
    try:
        (CACHE_DIR / f"{k}.json").write_text(json.dumps({"expires": exp, "value": value}, default=str))
    except Exception:
        pass
    return value