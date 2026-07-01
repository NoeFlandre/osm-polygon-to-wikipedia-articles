"""HTTP client for the Wikidata + Wikipedia APIs.

Thin convenience wrappers that delegate to ``wikipedia._retry`` for
transient-error handling.
"""
from __future__ import annotations

import urllib.parse

from ._retry import get_json_with_retry

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://{lang}.wikipedia.org/w/api.php"

USER_AGENT = "osm-polygon-to-wikipedia-articles/0.1 (https://github.com/NoeFlandre/osm-polygon-to-wikipedia-articles)"


def fetch_wikidata_sitelinks(qid: str) -> dict[str, dict[str, str]] | None:
    """Fetch ``sitelinks`` for a Wikidata entity.

    Returns the ``sitelinks`` sub-dict, or ``None`` if the entity doesn't exist
    or the request fails (after retries).
    """
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
        "format": "json",
    }
    payload = get_json_with_retry(
        f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}",
        headers={"Accept": "application/json"},
    )
    if payload is None:
        return None
    entity = payload.get("entities", {}).get(qid)
    if not entity:
        return None
    return entity.get("sitelinks", {})


def fetch_wikipedia_summary(lang: str, title: str) -> dict | None:
    """Fetch the REST summary for a Wikipedia article. Returns parsed JSON or None."""
    import urllib.parse as _u

    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{_u.quote(title)}"
    return get_json_with_retry(url, headers={"Accept": "application/json"})


def fetch_wikipedia_extract(lang: str, title: str) -> dict | None:
    """Fetch the plain-text body query for a Wikipedia article. Returns parsed JSON or None."""
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "titles": title,
        "format": "json",
    }
    url = f"{WIKIPEDIA_API.format(lang=lang)}?{urllib.parse.urlencode(params)}"
    return get_json_with_retry(url, headers={"Accept": "application/json"})
