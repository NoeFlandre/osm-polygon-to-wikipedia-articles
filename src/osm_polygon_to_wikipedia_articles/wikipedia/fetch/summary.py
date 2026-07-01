"""Wikipedia REST summary fetcher.

Endpoint: ``https://<lang>.wikipedia.org/api/rest_v1/page/summary/<title>``
Returns structured JSON: title, extract, description, thumbnail, coordinates, urls.

Uses ``wikipedia._retry`` for transient-error retries so brief rate-limits
or network blips don't lose the article.
"""
from __future__ import annotations

import urllib.parse
from typing import Callable

from ._retry import get_json_with_retry
from ..pipeline.types import ArticleSummary

GetJSON = Callable[[str, int], dict]


def _default_get(url: str, timeout: int = 20) -> dict | None:
    return get_json_with_retry(
        url,
        headers={"Accept": "application/json"},
        timeout=timeout,
    )


def fetch_summary(
    lang: str,
    title: str,
    *,
    _get: GetJSON = _default_get,
) -> ArticleSummary | None:
    """Fetch and parse a Wikipedia article summary.

    ``_get`` is injectable for tests. The default implementation retries
    transient errors (429/5xx/network blips) so a brief rate-limit doesn't
    permanently lose the article.
    """
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    try:
        payload = _get(url, 20)
    except Exception:
        return None
    if payload is None:
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
