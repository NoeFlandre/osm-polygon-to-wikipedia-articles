"""Tests for the retry-capable JSON GET helper used by all Wikipedia / Wikidata fetchers."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import urllib.error

from osm_polygon_to_wikipedia_articles.wikipedia._retry import (
    get_json_with_retry,
    RetriesExhausted,
)


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _http_error(code: int, *, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = {"Retry-After": retry_after} if retry_after else None
    req = urllib.request.Request("https://example.invalid/x")
    return urllib.error.HTTPError(req.full_url, code, "msg", headers, None)


# --- happy path ----------------------------------------------------------

def test_succeeds_on_first_try() -> None:
    """A 200 response yields the parsed JSON on the first call."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout=20):
        calls["n"] += 1
        return _FakeResponse(b'{"ok": true}')

    payload = get_json_with_retry(
        "https://example.invalid/api",
        urlopen=fake_urlopen,
        sleep=lambda s: None,
    )
    assert payload == {"ok": True}
    assert calls["n"] == 1


# --- retry on transient errors ------------------------------------------

def test_retries_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 (rate-limited) response triggers retry."""
    calls = {"n": 0, "sleeps": []}

    def fake_urlopen(req, timeout=20):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return _FakeResponse(b'{"ok": true}')

    payload = get_json_with_retry(
        "https://example.invalid/api",
        urlopen=fake_urlopen,
        sleep=lambda s: calls["sleeps"].append(s),
    )
    assert payload == {"ok": True}
    assert calls["n"] == 3
    # Two sleeps on the way, each at least base backoff
    assert len(calls["sleeps"]) == 2
    assert all(s >= 0.0 for s in calls["sleeps"])


def test_retries_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 503 (server error) triggers retry."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout=20):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(503)
        return _FakeResponse(b'{"ok": true}')

    payload = get_json_with_retry(
        "https://example.invalid/api",
        urlopen=fake_urlopen,
        sleep=lambda s: None,
    )
    assert payload == {"ok": True}
    assert calls["n"] == 2


def test_honors_retry_after_header() -> None:
    """If 429 has Retry-After, we wait at least that long (capped)."""
    calls = {"n": 0, "sleeps": []}

    def fake_urlopen(req, timeout=20):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, retry_after="3")
        return _FakeResponse(b'{"ok": true}')

    payload = get_json_with_retry(
        "https://example.invalid/api",
        urlopen=fake_urlopen,
        sleep=lambda s: calls["sleeps"].append(s),
    )
    assert payload == {"ok": True}
    assert calls["sleeps"][0] == 3.0


def test_returns_none_after_max_retries() -> None:
    """After 5 failed attempts, the helper returns None (does NOT raise)."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout=20):
        calls["n"] += 1
        raise _http_error(503)

    payload = get_json_with_retry(
        "https://example.invalid/api",
        urlopen=fake_urlopen,
        sleep=lambda s: None,
        max_retries=5,
    )
    assert payload is None
    assert calls["n"] == 5


# --- permanent errors do NOT retry ---------------------------------------

def test_404_does_not_retry() -> None:
    """A 404 is permanent — no retry, return None immediately."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout=20):
        calls["n"] += 1
        raise _http_error(404)

    payload = get_json_with_retry(
        "https://example.invalid/api",
        urlopen=fake_urlopen,
        sleep=lambda s: None,
    )
    assert payload is None
    assert calls["n"] == 1


def test_403_does_not_retry() -> None:
    """A 403 is permanent — no retry."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout=20):
        calls["n"] += 1
        raise _http_error(403)

    payload = get_json_with_retry(
        "https://example.invalid/api",
        urlopen=fake_urlopen,
        sleep=lambda s: None,
    )
    assert payload is None
    assert calls["n"] == 1


# --- network blips -------------------------------------------------------

def test_retries_on_url_error() -> None:
    """Connection reset / DNS failure should retry."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout=20):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("connection reset")
        return _FakeResponse(b'{"ok": true}')

    payload = get_json_with_retry(
        "https://example.invalid/api",
        urlopen=fake_urlopen,
        sleep=lambda s: None,
    )
    assert payload == {"ok": True}
    assert calls["n"] == 2


def test_exponential_backoff() -> None:
    """Backoff should double each attempt (base * 2**attempt)."""
    sleeps = []

    def fake_urlopen(req, timeout=20):
        raise _http_error(503)

    get_json_with_retry(
        "https://example.invalid/api",
        urlopen=fake_urlopen,
        sleep=lambda s: sleeps.append(s),
        max_retries=4,
        backoff_base=1.0,
    )
    # 3 sleeps for 4 attempts
    assert sleeps == [1.0, 2.0, 4.0]
