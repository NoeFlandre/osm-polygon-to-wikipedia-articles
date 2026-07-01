"""Shared HTTP-fetch helper.

Every Wikipedia / Wikidata fetcher needs the same default behaviour:
GET the URL with ``Accept: application/json`` and retry on transient
errors. Each fetcher used to embed its own copy of ``_default_get``;
this module centralises the body so all fetchers go through one
implementation.
"""
from __future__ import annotations

from ._retry import get_json_with_retry

DEFAULT_HEADERS = {"Accept": "application/json"}


def default_get_json(
    url: str,
    *,
    timeout: int = 20,
    headers: dict | None = None,
) -> dict | None:
    """GET ``url`` and parse as JSON, with transient-error retries.

    ``Accept: application/json`` is always added (overridable via
    ``headers``); any extra headers supplied by the caller are merged
    in. Returns ``None`` after exhausting retries (the retry layer's
    contract).
    """
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    return get_json_with_retry(url, headers=merged, timeout=timeout)


__all__ = ["DEFAULT_HEADERS", "default_get_json"]
