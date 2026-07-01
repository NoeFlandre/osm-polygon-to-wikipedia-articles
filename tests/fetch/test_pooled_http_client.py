"""Tests for the pooled HTTP client.

Each request to ``https://www.wikidata.org/w/api.php`` via vanilla
``urllib.request.urlopen`` opens a fresh TCP/TLS connection (~150 ms
of TLS handshake).  Over 50k requests that's ~2 hours wasted on
handshakes.

This module tests a thin wrapper around ``httpx.Client`` that
- pools connections (one per host),
- optionally negotiates HTTP/2 (huge speedup when supported),
- retries transient errors with exponential backoff,
- returns the parsed JSON dict or raises a clear exception.
"""
from __future__ import annotations

import json
from typing import Callable

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._pooled_http_client import (
    PooledHttpClient,
)


# ---------------------------------------------------------------------------
# Fake transport: deterministic, no real network
# ---------------------------------------------------------------------------

class _FakeTransport:
    """Drop-in for ``httpx.BaseTransport`` that records requests and
    returns scripted responses.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.handler: Callable[[dict], tuple[int, dict]] = (
            lambda req: (200, {"ok": True})
        )

    def handle_request(self, request):  # pragma: no cover - thin wrapper
        from httpx import Response
        body = json.loads(request.content.decode()) if request.content else {}
        info = {
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "body": body,
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
# Basic GET
# ---------------------------------------------------------------------------

def test_get_json_returns_parsed_dict() -> None:
    transport = _FakeTransport()
    with PooledHttpClient(transport=transport) as client:
        out = client.get_json("https://example.test/x")
    assert out == {"ok": True}


def test_get_json_sends_user_agent_header() -> None:
    transport = _FakeTransport()
    with PooledHttpClient(transport=transport, user_agent="test/1.0") as client:
        client.get_json("https://example.test/x")
    assert transport.calls[0]["headers"]["user-agent"] == "test/1.0"


def test_get_json_merges_extra_headers() -> None:
    transport = _FakeTransport()
    with PooledHttpClient(transport=transport) as client:
        client.get_json(
            "https://example.test/x",
            headers={"Accept": "application/json", "X-Foo": "bar"},
        )
    h = transport.calls[0]["headers"]
    assert h["accept"] == "application/json"
    assert h["x-foo"] == "bar"


# ---------------------------------------------------------------------------
# Retry on transient errors
# ---------------------------------------------------------------------------

def test_retries_on_429_then_succeeds() -> None:
    transport = _FakeTransport()

    state = {"calls": 0}

    def handler(req: dict) -> tuple[int, dict]:
        state["calls"] += 1
        if state["calls"] < 3:
            return 429, {"error": "rate-limited"}
        return 200, {"ok": True}

    transport.handler = handler
    with PooledHttpClient(
        transport=transport,
        max_retries=5,
        backoff_base=0.001,  # fast for tests
        sleep=lambda _s: None,
    ) as client:
        out = client.get_json("https://example.test/x")
    assert out == {"ok": True}
    assert state["calls"] == 3


def test_retries_on_500_then_succeeds() -> None:
    transport = _FakeTransport()

    state = {"calls": 0}

    def handler(req: dict) -> tuple[int, dict]:
        state["calls"] += 1
        if state["calls"] < 2:
            return 503, {"error": "unavailable"}
        return 200, {"ok": True}

    transport.handler = handler
    with PooledHttpClient(
        transport=transport,
        max_retries=3,
        backoff_base=0.001,
        sleep=lambda _s: None,
    ) as client:
        out = client.get_json("https://example.test/x")
    assert out == {"ok": True}


def test_raises_urllib_http_error_when_all_retries_exhausted_on_429() -> None:
    """When 429 retries are exhausted, the client must RAISE so the
    resilient layer can record the batch as missing — never silently
    return ``None`` (that's the old buggy behaviour that masked
    throttling in production).
    """
    import urllib.error
    transport = _FakeTransport()
    state = {"calls": 0}

    def handler(req: dict) -> tuple[int, dict]:
        state["calls"] += 1
        return 429, {"error": "rate-limited"}

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


def test_raises_urllib_http_error_on_404() -> None:
    """Non-429 4xx raises immediately (no retry) so the resilient
    layer can distinguish permanent failure from transient throttle.
    """
    import urllib.error
    transport = _FakeTransport()
    state = {"calls": 0}

    def handler(req: dict) -> tuple[int, dict]:
        state["calls"] += 1
        return 404, {"error": "not found"}

    transport.handler = handler
    with PooledHttpClient(
        transport=transport,
        max_retries=5,
        backoff_base=0.001,
        sleep=lambda _s: None,
    ) as client:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            client.get_json("https://example.test/x")
    assert excinfo.value.code == 404
    assert state["calls"] == 1


# ---------------------------------------------------------------------------
# Rate limiter integration
# ---------------------------------------------------------------------------

def test_reports_throttle_to_rate_limiter_on_429() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.fetch._rate_limiter import (
        RateLimiter,
    )
    transport = _FakeTransport()

    def handler(req: dict) -> tuple[int, dict]:
        return 429, {"error": "rate-limited"}

    transport.handler = handler
    rl = RateLimiter(max_per_second=10.0, burst=10)
    with PooledHttpClient(
        transport=transport,
        max_retries=2,
        backoff_base=0.001,
        sleep=lambda _s: None,
        rate_limiter=rl,
    ) as client:
        import urllib.error
        with pytest.raises(urllib.error.HTTPError):
            client.get_json("https://example.test/x")
    assert rl.throttle_events >= 1


# ---------------------------------------------------------------------------
# Context management
# ---------------------------------------------------------------------------

def test_works_as_context_manager() -> None:
    transport = _FakeTransport()
    with PooledHttpClient(transport=transport) as client:
        client.get_json("https://example.test/x")
    # After exit, the underlying client is closed (no exception)


def test_close_is_idempotent() -> None:
    transport = _FakeTransport()
    client = PooledHttpClient(transport=transport)
    client.close()
    client.close()  # second call must not raise


# ---------------------------------------------------------------------------
# HTTP/2 hint
# ---------------------------------------------------------------------------

def test_http2_flag_is_accepted() -> None:
    """Setting ``http2=True`` must not crash even when the transport
    is the fake one (the flag is only consulted when constructing
    the real httpx.Client).  This guards against accidental
    KeyError-style regressions in the wiring.
    """
    transport = _FakeTransport()
    client = PooledHttpClient(transport=transport, http2=True)
    client.close()
