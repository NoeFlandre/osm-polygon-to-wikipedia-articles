"""Shared HTTP-fetch helper.

Every Wikipedia / Wikidata fetcher needs the same default behaviour:
GET the URL with ``Accept: application/json`` and retry on transient
errors. Each fetcher used to embed its own copy of ``_default_get``;
this module centralises the body so all fetchers go through one
implementation.

The default implementation now uses a process-shared
:class:`PooledHttpClient` (HTTP/1.1 keep-alive + optional HTTP/2),
which is several times faster than the legacy
``urllib.request.urlopen`` path because it reuses TCP/TLS connections.
Tests that need to control the HTTP layer can still inject their own
``_get`` callable or set ``_FORCE_LEGACY_FETCHER`` to fall back to
the original ``urllib``-based implementation.
"""
from __future__ import annotations

import threading
from typing import Optional

from ._pooled_http_client import PooledHttpClient


DEFAULT_HEADERS = {"Accept": "application/json"}

# When True, fall back to the urllib-based retry layer.  Useful for
# tests that explicitly want the legacy behaviour.
_FORCE_LEGACY_FETCHER = False

# Process-shared PooledHttpClient.  Created lazily so tests that
# import this module without ever calling ``default_get_json`` pay
# nothing.
_client: Optional[PooledHttpClient] = None
_client_lock = threading.Lock()


def _get_client() -> PooledHttpClient:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = PooledHttpClient()
    return _client


def default_get_json(
    url: str,
    *,
    timeout: int = 20,
    headers: dict | None = None,
) -> dict | None:
    """GET ``url`` and parse as JSON, with transient-error retries.

    Uses the shared :class:`PooledHttpClient` so the underlying TCP
    connection is reused across calls (huge speedup vs. opening a
    fresh connection per request).

    ``Accept: application/json`` is always added (overridable via
    ``headers``); any extra headers supplied by the caller are merged
    in. Returns ``None`` after exhausting retries.
    """
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    if _FORCE_LEGACY_FETCHER:
        from ._retry import get_json_with_retry
        return get_json_with_retry(url, headers=merged, timeout=timeout)
    return _get_client().get_json(url, headers=merged)


__all__ = ["DEFAULT_HEADERS", "default_get_json"]
