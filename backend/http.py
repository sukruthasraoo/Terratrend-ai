"""Shared async HTTP client with timeouts, retries and error tracking."""
import asyncio, time
import httpx
from .config import USER_AGENT

_errors: list[dict] = []   # recent API errors for the freshness/observability view

def recent_errors(n: int = 50):
    return _errors[-n:]

async def fetch(url: str, params: dict | None = None, timeout: float = 30.0,
                retries: int = 2, as_json: bool = True, headers: dict | None = None, with_headers: bool = False):
    h = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=h) as c:
                r = await c.get(url, params=params)
                r.raise_for_status()
                body = r.json() if as_json else r.text
                return (body, dict(r.headers)) if with_headers else body
        except Exception as e:  # noqa
            last = e
            _errors.append({"url": url, "error": str(e)[:300], "time": time.time(), "attempt": attempt})
            if attempt < retries:
                await asyncio.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"Request failed: {url} :: {last}")