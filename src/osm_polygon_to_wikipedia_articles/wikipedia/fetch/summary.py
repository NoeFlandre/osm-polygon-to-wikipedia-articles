"""Wikipedia REST summary fetcher.

Endpoint: ``https://<lang>.wikipedia.org/api/rest_v1/page/summary/<title>``
Returns structured JSON: title, extract, description, thumbnail, coordinates, urls.

Uses ``wikipedia._retry`` for transient-error retries so brief rate-limits
or network blips don't lose the article.
"""
from __future__ import annotations

import urllib.parse
from typing import Callable

from ..pipeline.types import ArticleSummary
from ._helpers import default_get_json

GetJSON = Callable[[str, int], dict]


def fetch_summary(
    lang: str,
    title: str,
    *,
    _get: GetJSON | None = None,
) -> ArticleSummary | None:
    """Fetch and parse a Wikipedia article summary.

    ``_get`` is injectable for tests. The default implementation retries
    transient errors (429/5xx/network blips) so a brief rate-limit doesn't
    permanently lose the article.
    """
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
    try:
        if _get is None:
            payload = default_get_json(url, timeout=20)
        else:
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


__all__ = ["fetch_summary"]

