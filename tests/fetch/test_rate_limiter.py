"""Tests for the token-bucket :class:`RateLimiter`.

The rate limiter is the foundation of the new pipeline. It caps the
request rate to Wikidata at a configurable ceiling (default 5 req/s for
anonymous), and *adaptively* slows down when 429s are reported. This
keeps us just under the throttle threshold and turns what was a
"hammer the API, get blanket-throttled, sleep 30s, repeat" loop into a
steady stream of accepted requests.
"""
from __future__ import annotations

import time

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._rate_limiter import (
    RateLimiter,
)


# ---------------------------------------------------------------------------
# Token-bucket basics
# ---------------------------------------------------------------------------

def test_default_rate_is_5_per_second() -> None:
    rl = RateLimiter()
    assert rl.max_per_second == 5.0


def test_acquire_returns_quickly_within_burst() -> None:
    """5 acquires in immediate succession should all return in <50ms
    total — the bucket starts full.
    """
    rl = RateLimiter(max_per_second=5.0, burst=5)
    t0 = time.time()
    for _ in range(5):
        rl.acquire()
    assert time.time() - t0 < 0.05, "burst should be near-instant"


def test_acquire_blocks_when_bucket_empty() -> None:
    """After draining the burst, the 6th acquire must wait ~0.2s."""
    rl = RateLimiter(max_per_second=5.0, burst=5)
    for _ in range(5):
        rl.acquire()
    t0 = time.time()
    rl.acquire()
    elapsed = time.time() - t0
    assert 0.15 < elapsed < 0.40, (
        f"expected ~0.2s wait, got {elapsed:.3f}s"
    )


def test_acquire_blocking_can_be_skipped_in_tests() -> None:
    """A ``blocking=False`` acquire must never sleep; it returns
    immediately with a token if available, else None.
    """
    rl = RateLimiter(max_per_second=2.0, burst=2)
    assert rl.acquire(blocking=False) is True
    assert rl.acquire(blocking=False) is True
    assert rl.acquire(blocking=False) is False  # bucket empty


# ---------------------------------------------------------------------------
# Adaptive back-off on 429
# ---------------------------------------------------------------------------

def test_report_throttle_reduces_rate() -> None:
    """A 429 should drop the effective rate immediately."""
    rl = RateLimiter(max_per_second=5.0, burst=5)
    rl.report_throttle()
    assert rl.max_per_second < 5.0


def test_report_throttle_floor_is_at_least_0_5_per_second() -> None:
    """We never slow down below 0.5/s — that's a hard floor to keep the
    pipeline making forward progress even on a heavily-throttled IP.
    """
    rl = RateLimiter(max_per_second=5.0, burst=5)
    for _ in range(20):
        rl.report_throttle()
    assert rl.max_per_second >= 0.5


def test_report_throttle_decreases_geometrically() -> None:
    """Each 429 should halve the rate (down to the floor)."""
    rl = RateLimiter(max_per_second=8.0, burst=5)
    rl.report_throttle()
    r1 = rl.max_per_second
    rl.report_throttle()
    r2 = rl.max_per_second
    assert r2 < r1
    assert abs(r1 / r2 - 2.0) < 0.01  # roughly halved


def test_report_success_gradually_restores_rate() -> None:
    """After a 429-induced slow-down, sustained successes should
    gradually bring the rate back up to the original ceiling.
    """
    rl = RateLimiter(max_per_second=4.0, burst=5)
    rl.report_throttle()
    rl.report_throttle()
    slowed = rl.max_per_second
    # Many successes should restore the rate
    for _ in range(200):
        rl.report_success()
    assert rl.max_per_second > slowed
    assert rl.max_per_second <= 4.0  # never above the original ceiling


# ---------------------------------------------------------------------------
# Multiple parallel acquirers
# ---------------------------------------------------------------------------

def test_two_threads_share_the_bucket() -> None:
    """Two threads making 5 acquires each should take ~2s total at
    5 req/s (bucket size 5 means first 5 are instant, the rest wait).
    """
    import threading
    rl = RateLimiter(max_per_second=5.0, burst=5)
    t0 = time.time()
    threads = []
    for _ in range(2):
        def worker() -> None:
            for _ in range(5):
                rl.acquire()
        threads.append(threading.Thread(target=worker))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - t0
    # 10 acquires at 5/s with burst 5 → 5 instant + 5 spaced = ~1s
    assert 0.7 < elapsed < 1.5, (
        f"expected ~1s for 10 acquires at 5/s with burst 5, got {elapsed:.3f}s"
    )


# ---------------------------------------------------------------------------
# Snapshot for debugging
# ---------------------------------------------------------------------------

def test_snapshot_for_logging() -> None:
    rl = RateLimiter(max_per_second=3.5, burst=4)
    rl.acquire()
    rl.acquire()
    rl.report_throttle()
    s = rl.snapshot()
    assert "max_per_second" in s
    assert "tokens" in s
    assert "throttle_events" in s
    assert "success_events" in s
    assert s["max_per_second"] < 3.5
    assert s["throttle_events"] == 1
    assert s["success_events"] == 0
