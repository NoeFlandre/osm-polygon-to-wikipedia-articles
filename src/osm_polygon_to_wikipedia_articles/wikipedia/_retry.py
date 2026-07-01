"""Reusable retry-on-transient-error helper for urllib JSON GETs.

Used by every Wikipedia / Wikidata fetcher so a brief rate-limit or network
blip doesn't permanently lose an article.

Transient (retry-able):
  - HTTP 429 (rate-limited)
  - HTTP 5xx (server errors)
  - ``URLError`` (DNS, connection reset, peer reset, …)
  - ``ConnectionResetError``, ``TimeoutError``

Permanent (no retry):
  - HTTP 4xx other than 429 (e.g. 404, 403)

The function returns ``None`` after exhausting retries (it does NOT raise) so
callers can fall through to "no article found" cleanly.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable


# Sentinel raised only when the caller explicitly wants exceptions (rare).
class RetriesExhausted(Exception):
    """Raised when retry attempt count is exceeded and ``raise_on_exhaustion=True``."""


# Default sleep: ``time.sleep``; injectable for tests.
SleepFn = Callable[[float], None]
UrlOpenFn = Callable[..., object]


def _default_urlopen(req: urllib.request.Request, timeout: int = 20):
    return urllib.request.urlopen(req, timeout=timeout)


def _compute_delay(
    *,
    e: urllib.error.HTTPError,
    attempt: int,
    backoff_base: float,
) -> float:
    """Compute the next sleep: Retry-After if present, else exponential backoff.

    Capped at 30 seconds so we never block forever on a huge Retry-After.
    """
    try:
        if e.headers:
            ra = e.headers.get("Retry-After")
            if ra:
                return min(float(ra), 30.0)
    except Exception:
        pass
    return backoff_base * (2 ** attempt)


def get_json_with_retry(
    url: str,
    *,
    headers: dict | None = None,
    timeout: int = 20,
    max_retries: int = 5,
    backoff_base: float = 0.5,
    sleep: SleepFn | None = None,
    urlopen: UrlOpenFn | None = None,
) -> dict | None:
    """GET ``url`` and parse the response as JSON, retrying transient errors.

    Parameters
    ----------
    url:
        The URL to GET.
    headers:
        Optional request headers (merged with the default ``User-Agent``).
    timeout:
        Per-attempt socket timeout in seconds.
    max_retries:
        Maximum number of total attempts (default 5).
    backoff_base:
        Base for exponential backoff between retries (default 0.5s → 0.5, 1, 2, 4, 8).
    sleep:
        Sleep function (defaults to ``time.sleep``); injected for tests.
    urlopen:
        Replacement for ``urllib.request.urlopen``; injected for tests.

    Returns
    -------
    The parsed JSON dict, or ``None`` if the request permanently failed or
    transient failures exhausted all retries.
    """
    if sleep is None:
        import time as _time
        sleep = _time.sleep
    if urlopen is None:
        urlopen = _default_urlopen

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "osm-polygon-to-wikipedia-articles/0.1")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    for attempt in range(max_retries):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                # Transient — retry with backoff
                if attempt < max_retries - 1:
                    sleep(_compute_delay(e=e, attempt=attempt, backoff_base=backoff_base))
                    continue
                return None
            # Permanent 4xx — no retry
            return None
        except (urllib.error.URLError, ConnectionResetError, TimeoutError):
            if attempt < max_retries - 1:
                sleep(backoff_base * (2 ** attempt))
                continue
            return None
        except Exception:
            # Unexpected — don't loop forever
            return None
    return None
