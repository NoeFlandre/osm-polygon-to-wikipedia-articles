"""Pooled HTTP client built on top of ``httpx.Client``.

Why
---
The existing ``get_json_with_retry`` uses ``urllib.request.urlopen``,
which opens a fresh TCP/TLS connection for every request.  TLS
handshake alone is ~150 ms; over 50 000 requests that's ~2 hours
of wasted setup time.

``httpx.Client`` keeps a connection pool per host (HTTP keep-alive)
and (optionally) negotiates HTTP/2 with multiplexing.  This module
wraps it with the same retry semantics as ``get_json_with_retry``
so callers can swap it in without changes.

Thread safety
-------------
``httpx.Client`` is documented as thread-safe for issuing
concurrent requests.  We use a single shared instance per pipeline.
"""
from __future__ import annotations

import json
import urllib.error
from typing import Callable, Optional

from ._rate_limiter import RateLimiter


SleepFn = Callable[[float], None]


class PooledHttpClient:
    """HTTP/1.1 + optional HTTP/2 pooled client with retry on 429/5xx.

    Parameters
    ----------
    transport
        Optional ``httpx.BaseTransport`` for testing.  Production
        code should leave this ``None`` to get the default
        ``httpx.Client``.
    user_agent
        Value of the ``User-Agent`` header on every request.
    max_retries
        Maximum number of total attempts per request.
    backoff_base
        Base for exponential backoff between retries.
    sleep
        Sleep function (injectable for tests).
    rate_limiter
        Optional :class:`RateLimiter` to report 429/5xx throttles
        back to.  When ``None``, we still retry but the rate is
        not adapted.
    http2
        Whether to negotiate HTTP/2 (default ``True`` if the
        ``h2`` package is installed; otherwise ignored).
    timeout
        Per-request socket timeout in seconds.
    """

    def __init__(
        self,
        *,
        transport=None,
        # Wikimedia's User-Agent policy
        # (https://meta.wikimedia.org/wiki/User-Agent_policy) requires
        # a descriptive app name, a version, and contact info.  Bare
        # User-Agents are rejected with HTTP 403.
        user_agent: str = (
            "osm-polygon-to-wikipedia-articles/0.1 "
            "(https://github.com/NoeFlandre/osm-polygon-to-wikipedia-articles; "
            "contact: noeflandre@gmail.com)"
        ),
        max_retries: int = 5,
        backoff_base: float = 0.5,
        sleep: Optional[SleepFn] = None,
        rate_limiter: Optional[RateLimiter] = None,
        http2: bool = True,
        timeout: float = 20.0,
    ) -> None:
        self._user_agent = user_agent
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._rate_limiter = rate_limiter
        self._http2 = http2
        self._timeout = timeout
        if sleep is None:
            import time as _time
            self._sleep = _time.sleep
        else:
            self._sleep = sleep
        self._client = None
        self._owns_client = transport is None
        if transport is None:
            self._client = self._build_real_client()
        else:
            # Test path: build a thin wrapper that exposes the same
            # ``get`` / ``close`` API as ``httpx.Client``.
            self._client = _FakeClient(transport)

    def _build_real_client(self):
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "PooledHttpClient requires httpx. Install with "
                "`uv add httpx` (or remove this dependency)."
            ) from exc
        kwargs: dict = {"timeout": self._timeout}
        # Try HTTP/2 first; if h2 isn't installed, fall back to HTTP/1.1.
        if self._http2:
            try:
                return httpx.Client(http2=True, **kwargs)
            except ImportError:
                # h2 not installed — silently fall back.
                pass
        return httpx.Client(**kwargs)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "PooledHttpClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def get_json(
        self,
        url: str,
        *,
        headers: Optional[dict] = None,
    ) -> Optional[dict]:
        """GET ``url`` and parse the response as JSON.

        Returns the parsed dict on 2xx / 3xx, or ``None`` on
        connection / JSON-parse failures.

        **Raises** :class:`urllib.error.HTTPError` on 4xx and 5xx
        responses (including after retries are exhausted).  This is
        the contract the resilient sitelinks layer relies on to
        detect throttles vs. permanent failures.
        """
        import urllib.error as _urllib_error

        merged_headers = {"User-Agent": self._user_agent, "Accept": "application/json"}
        if headers:
            merged_headers.update(headers)

        last_delay = self._backoff_base
        for attempt in range(self._max_retries):
            try:
                resp = self._client.get(url, headers=merged_headers)
            except Exception:
                if attempt < self._max_retries - 1:
                    self._sleep(last_delay)
                    last_delay *= 2
                    continue
                return None

            if resp.status_code == 429 or resp.status_code >= 500:
                # Throttle — tell the rate limiter and back off.
                if self._rate_limiter is not None:
                    self._rate_limiter.report_throttle()
                if attempt < self._max_retries - 1:
                    # Honor Retry-After if present.
                    retry_after = resp.headers.get("retry-after")
                    try:
                        delay = min(float(retry_after), 30.0) if retry_after else last_delay
                    except (TypeError, ValueError):
                        delay = last_delay
                    self._sleep(delay)
                    last_delay = max(last_delay * 2, self._backoff_base)
                    continue
                # Out of retries — raise so the resilient layer can
                # record this batch as missing rather than silently
                # treating a 429 as a successful empty response.
                raise _urllib_error.HTTPError(
                    url=url, code=resp.status_code,
                    msg=f"HTTP {resp.status_code}",
                    hdrs=resp.headers, fp=None,
                )

            if 400 <= resp.status_code < 500:
                # Permanent client error (other than 429).  Always
                # raise — the resilient layer needs to know this is
                # not a transient failure so it doesn't loop forever.
                raise _urllib_error.HTTPError(
                    url=url, code=resp.status_code,
                    msg=f"HTTP {resp.status_code}",
                    hdrs=resp.headers, fp=None,
                )

            # 2xx / 3xx
            try:
                return resp.json()
            except (json.JSONDecodeError, ValueError):
                return None

        return None

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return transport stats for logging (best-effort)."""
        if self._client is None:
            return {}
        return {
            "http2": self._http2,
        }


class _FakeClient:
    """Thin test double that exposes the ``get`` / ``close`` API of
    ``httpx.Client`` but uses a pre-built :class:`_FakeTransport`.
    """

    def __init__(self, transport) -> None:
        self._transport = transport

    def get(self, url: str, headers: Optional[dict] = None):
        import httpx
        req = httpx.Request("GET", url, headers=headers or {})
        return self._transport.handle_request(req)

    def close(self) -> None:
        try:
            self._transport.close()
        except Exception:
            pass


__all__ = ["PooledHttpClient"]
