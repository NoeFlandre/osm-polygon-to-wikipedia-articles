"""HTTP client for the Wikidata + Wikipedia APIs.

Thin wrapper around urllib so we don't pull in a heavy HTTP dep.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://{lang}.wikipedia.org/w/api.php"

USER_AGENT = "osm-polygon-to-wikipedia-articles/0.1 (https://github.com/NoeFlandre/osm-polygon-to-wikipedia-articles)"


def fetch_wikidata_sitelinks(qid: str) -> dict[str, dict[str, str]] | None:
    """Fetch ``sitelinks`` for a Wikidata entity.

    Returns the ``sitelinks`` sub-dict, or ``None`` if the entity doesn't exist
    or the request fails.
    """
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
        "format": "json",
    }
    try:
        with urllib.request.urlopen(
            _request(f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"), timeout=20
        ) as resp:
            payload = json.loads(resp.read())
    except Exception:
        return None
    entity = payload.get("entities", {}).get(qid)
    if not entity:
        return None
    return entity.get("sitelinks", {})


def fetch_wikipedia_summary(lang: str, title: str) -> dict | None:
    """Fetch the REST summary for a Wikipedia article. Returns parsed JSON or None."""
    import urllib.parse as _u

    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{_u.quote(title)}"
    try:
        with urllib.request.urlopen(_request(url), timeout=20) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})