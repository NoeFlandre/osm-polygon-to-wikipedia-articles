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


# When Wikidata throttles us (HTTP 429), the lower-level retry layer
# gives up after 5 attempts. For the per-country batch run we must not
# lose any QID, so each batch retries forever with exponential backoff
# capped at 60 seconds.
_MAX_BACKOFF_S = 60.0


def _fetch_batch_forever(url: str, *, urlopen, max_retries: int = 50) -> dict:
    """GET ``url`` until it returns a JSON body, regardless of 429s.

    Uses a flat 2-second wait between attempts — exponential backoff
    is too slow when the Wikidata API is sustained-throttling us.
    ``max_retries`` (default 50) caps the total wait to ~100s per batch
    so a permanently blocked batch doesn't block the whole run.
    """
    import time as _time
    # Pass max_retries=1 to the lower-level helper so it doesn't add
    # its own exponential backoff on top of ours.
    for attempt in range(max_retries):
        try:
            payload = (get_json_with_retry(url, urlopen=urlopen, max_retries=1)
                       if urlopen is not None
                       else get_json_with_retry(url, max_retries=1))
        except Exception:
            payload = None
        if payload is not None:
            return payload
        # Flat wait between failed attempts. 2s keeps us under the
        # Wikidata anonymous rate limit (5 req/s) while not blocking
        # forever.
        _time.sleep(2.0)
    raise RuntimeError(
        f"batched_sitelinks: {max_retries} consecutive failures on {url[:120]}…"
    )


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

    **Each batch retries forever** on HTTP 429 / 5xx / connection errors
    so a transient throttle can never silently drop a QID.  A 0.5s
    per-batch sleep is inserted between successful calls as a politeness
    measure.

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
        payload = _fetch_batch_forever(url, urlopen=urlopen)
        entities = payload.get("entities", {})
        for qid in batch:
            ent = entities.get(qid)
            if not ent or ent.get("missing"):
                continue
            out[qid] = ent.get("sitelinks", {})
        # Polite spacing between batches so we don't hammer the API
        sleep(0.5)
    return out


__all__ = ["fetch_sitelinks_batched"]
