"""Wikipedia REST summary fetcher.

Endpoint: ``https://<lang>.wikipedia.org/api/rest_v1/page/summary/<title>``
Returns structured JSON: title, extract, description, thumbnail, coordinates, urls.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Callable

from .http_client import USER_AGENT
from .types import ArticleSummary

GetJSON = Callable[[str, int], dict]


def _default_get(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def fetch_summary(
    lang: str,
    title: str,
    *,
    _get: GetJSON = _default_get,
) -> ArticleSummary | None:
    """Fetch and parse a Wikipedia article summary."""
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    try:
        payload = _get(url, 20)
    except Exception:
        return None

    thumb = payload.get("thumbnail") or {}
    coords = payload.get("coordinates") or {}
    urls = (payload.get("content_urls") or {}).get("desktop") or {}

    return ArticleSummary(
        title=payload.get("title", title),
        pageid=payload.get("pageid"),
        description=payload.get("description"),
        extract=payload.get("extract"),
        thumbnail_url=thumb.get("source"),
        lat=coords.get("lat"),
        lon=coords.get("lon"),
        url=urls.get("page"),
    )