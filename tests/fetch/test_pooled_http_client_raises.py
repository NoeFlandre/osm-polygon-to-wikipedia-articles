"""Tests for the PooledHttpClient's exception semantics.

The resilient sitelinks fetcher relies on the URL fetcher raising
``urllib.error.HTTPError`` (or a compatible type) on 429/5xx so it
can:
1. report the throttle to the rate limiter,
2. decide whether to retry the batch or record QIDs as missing.

If the client silently returns a non-2xx response (status_code set,
no exception raised), the resilient layer's ``except`` clause never
fires and every QID ends up marked ``_missing: transient_failure``
even though the server is responding fine — a silent regression
that makes the whole pipeline produce zero usable data.

These tests pin down the contract:

- 429 / 5xx responses **must** raise ``urllib.error.HTTPError``
  so the existing resilient layer keeps working.
- 2xx responses **must** return the parsed JSON dict.
- 4xx (other than 429) **must** raise ``urllib.error.HTTPError``
  too, so the resilient layer records the QIDs as missing rather
  than spinning forever.
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._pooled_http_client import (
    PooledHttpClient,
)


class _FakeTransport:
    """Records requests and returns scripted responses via handle_request."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.handler = lambda req: (200, {"ok": True})

    def handle_request(self, request):
        from httpx import Response
        info = {
            "url": str(request.url),
            "headers": dict(request.headers),
        }
        self.calls.append(info)
        status, payload = self.handler(info)
        return Response(
            status_code=status,
            content=json.dumps(payload).encode(),
            headers={"content-type": "application/json"},
        )

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# 2xx → returns dict
# ---------------------------------------------------------------------------

def test_2xx_returns_dict() -> None:
    transport = _FakeTransport()
    with PooledHttpClient(transport=transport) as client:
        out = client.get_json("https://example.test/x")
    assert out == {"ok": True}


# ---------------------------------------------------------------------------
# 429 → raises urllib.error.HTTPError (regression guard)
# ---------------------------------------------------------------------------

def test_429_raises_urllib_http_error() -> None:
    transport = _FakeTransport()
    transport.handler = lambda req: (429, {"error": "throttled"})

    with PooledHttpClient(
        transport=transport,
        max_retries=1,
        backoff_base=0.001,
        sleep=lambda _s: None,
    ) as client:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            client.get_json("https://example.test/x")
    assert excinfo.value.code == 429


def test_5xx_raises_urllib_http_error() -> None:
    transport = _FakeTransport()
    transport.handler = lambda req: (503, {"error": "unavailable"})

    with PooledHttpClient(
        transport=transport,
        max_retries=1,
        backoff_base=0.001,
        sleep=lambda _s: None,
    ) as client:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            client.get_json("https://example.test/x")
    assert excinfo.value.code == 503


def test_4xx_raises_urllib_http_error() -> None:
    """Non-429 4xx must also raise so the resilient layer can
    distinguish "permanent 404" from "transient 429".
    """
    transport = _FakeTransport()
    transport.handler = lambda req: (404, {"error": "not found"})

    with PooledHttpClient(
        transport=transport,
        max_retries=1,
        backoff_base=0.001,
        sleep=lambda _s: None,
    ) as client:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            client.get_json("https://example.test/x")
    assert excinfo.value.code == 404


# ---------------------------------------------------------------------------
# Retry-then-raise: the resilient layer relies on this to back off
# ---------------------------------------------------------------------------

def test_retries_on_429_then_raises_urllib_http_error() -> None:
    """When the budget is exhausted, the last 429 should propagate
    as an HTTPError (not be silently swallowed to None) so the
    resilient layer can record the batch as missing.
    """
    transport = _FakeTransport()
    state = {"calls": 0}

    def handler(req):
        state["calls"] += 1
        return 429, {"error": "throttled"}

    transport.handler = handler
    with PooledHttpClient(
        transport=transport,
        max_retries=3,
        backoff_base=0.001,
        sleep=lambda _s: None,
    ) as client:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            client.get_json("https://example.test/x")
    assert excinfo.value.code == 429
    assert state["calls"] == 3


# ---------------------------------------------------------------------------
# Retry-then-success still returns the dict
# ---------------------------------------------------------------------------

def test_retries_on_429_then_returns_dict() -> None:
    transport = _FakeTransport()
    state = {"calls": 0}

    def handler(req):
        state["calls"] += 1
        if state["calls"] < 3:
            return 429, {"error": "throttled"}
        return 200, {"ok": True}

    transport.handler = handler
    with PooledHttpClient(
        transport=transport,
        max_retries=5,
        backoff_base=0.001,
        sleep=lambda _s: None,
    ) as client:
        out = client.get_json("https://example.test/x")
    assert out == {"ok": True}
    assert state["calls"] == 3


# ---------------------------------------------------------------------------
# The exception object is real HTTPError with the right attributes
# ---------------------------------------------------------------------------

def test_raised_http_error_has_url_and_code() -> None:
    """The exception must carry the URL and code attributes the
    resilient layer uses for its bookkeeping.
    """
    transport = _FakeTransport()
    transport.handler = lambda req: (429, {})
    with PooledHttpClient(
        transport=transport,
        max_retries=1,
        backoff_base=0.001,
        sleep=lambda _s: None,
    ) as client:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            client.get_json("https://example.test/x")
    err = excinfo.value
    assert err.code == 429
    assert str(err).startswith("HTTP Error 429")
