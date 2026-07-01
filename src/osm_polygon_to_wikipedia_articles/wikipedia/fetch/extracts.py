"""Wikipedia plain-text body fetcher.

Endpoint: ``https://<lang>.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext&...``
Returns the article body as plain text (no HTML), or ``None`` if the page is missing.

Uses ``wikipedia._retry`` for transient-error retries.
"""
from __future__ import annotations

import urllib.parse
from typing import Callable

from ._helpers import default_get_json

GetJSON = Callable[[str, int], dict]


def fetch_extract(
    lang: str,
    title: str,
    *,
    _get: GetJSON | None = None,
) -> str | None:
    """Fetch the plain-text body of a Wikipedia article. Returns None on failure (after retries)."""
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "titles": title,
        "format": "json",
    }
    url = f"https://{lang}.wikipedia.org/w/api.php?{urllib.parse.urlencode(params)}"
    try:
        if _get is None:
            payload = default_get_json(url, timeout=20)
        else:
            payload = _get(url, 20)
    except Exception:
        return None
    if payload is None:
        return None

    pages = payload.get("query", {}).get("pages", {})
    if not pages:
        return None
    # pages is a dict keyed by pageid (string); "missing" pages have pageid=-1
    page = next(iter(pages.values()))
    if "missing" in page or "extract" not in page:
        return None
    extract = page["extract"]
    return extract if extract else None


__all__ = ["fetch_extract"]

