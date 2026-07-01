"""HTTP layer: talk to Wikidata and Wikipedia.

This subpackage is the only place in the codebase that does I/O. Every
fetching function is injectable (its network call is hidden behind a
``_get`` or ``urlopen`` parameter) so tests can swap in a fake.

Modules
-------
_retry
    Reusable retry-on-transient-error helper (urllib + JSON).
http_client
    Thin convenience wrappers over the retry layer (legacy API).
batched_sitelinks
    Batched ``wbgetentities`` (up to 50 QIDs/request) — used for the
    per-country end-to-end re-process because the single-QID endpoint
    is rate-limited under sustained load.
summary
    ``https://<lang>.wikipedia.org/api/rest_v1/page/summary/<title>``
extracts
    ``https://<lang>.wikipedia.org/w/api.php?prop=extracts&explaintext`` (plain text body)

Public API
----------
- :func:`get_json_with_retry`
- :func:`fetch_wikidata_sitelinks`
- :func:`fetch_sitelinks_batched`
- :func:`fetch_summary`
- :func:`fetch_extract`
"""
from __future__ import annotations

from ._retry import get_json_with_retry
from .batched_sitelinks import fetch_sitelinks_batched
from .extracts import fetch_extract
from .http_client import (
    fetch_wikidata_sitelinks,
    fetch_wikipedia_summary,
    fetch_wikipedia_extract,
)
from .summary import fetch_summary

__all__ = [
    "fetch_extract",
    "fetch_sitelinks_batched",
    "fetch_summary",
    "fetch_wikidata_sitelinks",
    "fetch_wikipedia_extract",
    "fetch_wikipedia_summary",
    "get_json_with_retry",
]
