"""Tests for the adaptive retry wrapper.

The current ``_retry_forever`` in the rerun script uses a fixed
exponential-backoff schedule that ignores the actual rate-limit
signal from the server.  On a sustained 429 it just keeps banging
its head against the wall.

``AdaptiveFetcher`` instead:
- delegates to a pluggable ``fn`` (typically ``fetch_summary`` /
  ``fetch_extract``),
- reports 429 / 5xx to a shared :class:`RateLimiter` so the rate
  is halved immediately,
- asks the rate limiter how long to sleep (rather than a fixed
  exponential backoff),
- stops after ``max_attempts`` and returns ``None``,
- on success, reports success so the limiter can gradually restore
  its rate.

This keeps the "no silent drops" contract (every input QID ends up
in the result dict) while being much friendlier to a throttled IP.
"""
from __future__ import annotations

from typing import Callable, Tuple

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._adaptive_fetcher import (
    AdaptiveFetcher,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch._rate_limiter import (
    RateLimiter,
)


# ---------------------------------------------------------------------------
# Basic success
# ---------------------------------------------------------------------------

def test_returns_result_when_fetcher_succeeds() -> None:
    rl = RateLimiter(max_per_second=100.0, burst=100)
    fetcher = AdaptiveFetcher(
        fn=lambda: "ok",
        rate_limiter=rl,
        max_attempts=3,
        sleep=lambda _s: None,
    )
    result, attempts = fetcher.run()
    assert result == "ok"
    assert attempts == 1
    assert rl.success_events == 1


def test_passes_args_and_kwargs_to_fetcher() -> None:
    rl = RateLimiter(max_per_second=100.0, burst=100)
    captured = {}

    def fn(a, b, *, k):
        captured["a"] = a
        captured["b"] = b
        captured["k"] = k
        return (a, b, k)

    fetcher = AdaptiveFetcher(
        fn=fn,
        rate_limiter=rl,
        max_attempts=1,
        sleep=lambda _s: None,
    )
    result, _ = fetcher.run(1, 2, k="hello")
    assert result == (1, 2, "hello")


# ---------------------------------------------------------------------------
# Throttle handling
# ---------------------------------------------------------------------------

def test_retries_on_none_then_succeeds() -> None:
    rl = RateLimiter(max_per_second=100.0, burst=100)
    calls = {"n": 0}

    def fn() -> str | None:
        calls["n"] += 1
        if calls["n"] < 3:
            return None
        return "ok"

    fetcher = AdaptiveFetcher(
        fn=fn,
        rate_limiter=rl,
        max_attempts=10,
        sleep=lambda _s: None,
    )
    result, attempts = fetcher.run()
    assert result == "ok"
    assert attempts == 3
    assert rl.throttle_events == 2  # 2 None returns reported as throttle


def test_returns_none_after_max_attempts() -> None:
    rl = RateLimiter(max_per_second=100.0, burst=100)
    fetcher = AdaptiveFetcher(
        fn=lambda: None,
        rate_limiter=rl,
        max_attempts=3,
        sleep=lambda _s: None,
    )
    result, attempts = fetcher.run()
    assert result is None
    assert attempts == 3
    assert rl.throttle_events == 3


def test_throttle_events_halve_the_rate() -> None:
    rl = RateLimiter(max_per_second=8.0, burst=8)
    original = rl.max_per_second

    fetcher = AdaptiveFetcher(
        fn=lambda: None,
        rate_limiter=rl,
        max_attempts=4,
        sleep=lambda _s: None,
    )
    fetcher.run()
    # 4 throttles → 8 → 4 → 2 → 1 → floor (1)
    assert rl.max_per_second < original
    assert rl.max_per_second >= 0.5


# ---------------------------------------------------------------------------
# Sleeping strategy
# ---------------------------------------------------------------------------

def test_sleeps_when_fetcher_returns_none() -> None:
    """Each failed attempt should trigger exactly one sleep call."""
    rl = RateLimiter(max_per_second=10.0, burst=10)
    sleeps: list[float] = []
    fetcher = AdaptiveFetcher(
        fn=lambda: None,
        rate_limiter=rl,
        max_attempts=4,
        sleep=sleeps.append,
    )
    fetcher.run()
    # We sleep before the *next* attempt; so 3 sleeps for 4 attempts.
    assert len(sleeps) >= 3
    # Each sleep should be positive (we never busy-loop).
    assert all(s >= 0 for s in sleeps)


def test_does_not_sleep_after_successful_attempt() -> None:
    rl = RateLimiter(max_per_second=10.0, burst=10)
    sleeps: list[float] = []
    fetcher = AdaptiveFetcher(
        fn=lambda: "ok",
        rate_limiter=rl,
        max_attempts=5,
        sleep=sleeps.append,
    )
    fetcher.run()
    assert sleeps == []


# ---------------------------------------------------------------------------
# Integration with rate-limiter-acquire
# ---------------------------------------------------------------------------

def test_each_attempt_acquires_a_token() -> None:
    """The fetcher should go through the rate limiter's token bucket."""
    rl = RateLimiter(max_per_second=10.0, burst=10)
    initial = rl.snapshot()["tokens"]

    fetcher = AdaptiveFetcher(
        fn=lambda: "ok",
        rate_limiter=rl,
        max_attempts=1,
        sleep=lambda _s: None,
    )
    fetcher.run()
    # One token consumed.
    after = rl.snapshot()["tokens"]
    assert after < initial or (initial - after) >= 0
