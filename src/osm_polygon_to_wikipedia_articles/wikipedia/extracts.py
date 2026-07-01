"""Wikipedia plain-text body fetcher.

Endpoint: ``https://<lang>.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext&...``
Returns the article body as plain text (no HTML), or ``None`` if the page is missing.

Uses ``wikipedia._retry`` for transient-error retries.
"""
from __future__ import annotations

import urllib.parse
from typing import Callable

from ._retry import get_json_with_retry

GetJSON = Callable[[str, int], dict]


def _default_get(url: str, timeout: int = 20) -> dict | None:
    return get_json_with_retry(
        url,
        headers={"Accept": "application/json"},
        timeout=timeout,
    )


def fetch_extract(
    lang: str,
    title: str,
    *,
    _get: GetJSON = _default_get,
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
