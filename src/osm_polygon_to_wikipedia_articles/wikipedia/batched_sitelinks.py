"""Batched Wikidata sitelinks fetcher.

The per-QID ``wbgetentities`` endpoint caps at ~50 req/s under sustained
load. The `wbgetentities` endpoint actually supports up to 50 IDs per
request via comma-separation; we use that to fetch up to 50 QIDs at once.

This module returns the same dict shape as ``fetch_wikidata_sitelinks``
({qid: {lang: sitelink_dict}}) so we can drop it in transparently.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Callable

from ._retry import get_json_with_retry


def fetch_sitelinks_batched(
    qids: list[str],
    *,
    batch_size: int = 50,
    sleep: Callable[[float], None] | None = None,
    urlopen: Callable | None = None,
) -> dict[str, dict[str, dict]] | None:
    """Fetch sitelinks for many QIDs in batches of ``batch_size``.

    Returns a dict keyed by QID; each value is the ``sitelinks`` sub-dict for
    that QID, mirroring ``fetch_wikidata_sitelinks``.

    QIDs that fail to resolve (or where the request returns None) are
    omitted from the result dict so callers can do ``sitelinks_dict.get(qid)``.

    ``urlopen`` is forwarded to ``get_json_with_retry`` so tests can swap
    out the real network call for a fake; the production code path passes
    the real ``urllib.request.urlopen`` from the retry layer.
    """
    if not qids:
        return {}
    out: dict[str, dict[str, dict]] = {}
    if sleep is None:
        import time as _time
        sleep = _time.sleep

    for i in range(0, len(qids), batch_size):
        batch = qids[i : i + batch_size]
        ids_param = "|".join(batch)
        params = {
            "action": "wbgetentities",
            "ids": ids_param,
            "props": "sitelinks",
            "format": "json",
        }
        url = (
            "https://www.wikidata.org/w/api.php?"
            + urllib.parse.urlencode(params)
        )
        if urlopen is not None:
            payload = get_json_with_retry(url, urlopen=urlopen)
        else:
            payload = get_json_with_retry(url)
        if payload is None:
            continue
        entities = payload.get("entities", {})
        for qid in batch:
            ent = entities.get(qid)
            if not ent or ent.get("missing"):
                continue
            out[qid] = ent.get("sitelinks", {})
        # Polite spacing between batches so we don't hammer the API
        sleep(0.2)
    return out
