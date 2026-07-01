"""Tests for the parallel resilient sitelinks fetcher.

The single-threaded fetcher works but spends most of its time
waiting on the network.  With N workers sharing a single
:class:`RateLimiter`, we pipeline the I/O while still respecting
the same global rate budget — so the run is ~Nx faster without
hammering the API.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._rate_limiter import (
    RateLimiter,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch._resilient_sitelinks import (
    fetch_sitelinks_resilient,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch._sitelinks_checkpoint import (
    SitelinksCheckpoint,
)


class _SlowOk:
    """Simulates a real HTTP fetch with realistic per-call latency."""

    def __init__(self, latency: float = 0.05) -> None:
        self.latency = latency
        self.max_concurrent = 0
        self.current = 0
        self.lock = threading.Lock()
        self.calls: list[str] = []

    def __call__(self, url: str) -> dict:
        with self.lock:
            self.current += 1
            self.max_concurrent = max(self.max_concurrent, self.current)
        time.sleep(self.latency)
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(url).query)
        ids = q["ids"][0].split("|")
        out = {
            "entities": {
                qid: {"sitelinks": {"enwiki": {"title": f"T-{qid}"}}}
                for qid in ids
            }
        }
        with self.lock:
            self.current -= 1
        self.calls.append(url)
        return out


class _Counting429:
    """Returns 429 for the first N calls then OK."""

    def __init__(self, throttle_first: int = 0) -> None:
        self.throttle_first = throttle_first
        self.n = 0
        self.lock = threading.Lock()

    def __call__(self, url: str) -> dict:
        import urllib.error
        with self.lock:
            self.n += 1
            n = self.n
        if n <= self.throttle_first:
            raise urllib.error.HTTPError(
                url=url, code=429, msg="Too Many Requests", hdrs={}, fp=None,
            )
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(url).query)
        ids = q["ids"][0].split("|")
        return {
            "entities": {
                qid: {"sitelinks": {"enwiki": {"title": f"T-{qid}"}}}
                for qid in ids
            }
        }


# ---------------------------------------------------------------------------
# Single-worker behavior is identical to the non-parallel version
# ---------------------------------------------------------------------------

def test_single_worker_returns_all_qids(tmp_path) -> None:
    fetcher = _SlowOk(latency=0.001)
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    rl = RateLimiter(max_per_second=10_000.0, burst=10_000)  # no throttle

    qids = [f"Q{i}" for i in range(20)]
    out = fetch_sitelinks_resilient(
        qids,
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp,
        progress=lambda d, t: None,
        batch_size=5,
        max_workers=1,
    )
    cp.close()
    assert len(out) == 20
    for qid in qids:
        assert out[qid]["enwiki"]["title"] == f"T-{qid}"


# ---------------------------------------------------------------------------
# Parallel behavior: runs in parallel but respects rate budget
# ---------------------------------------------------------------------------

def test_multi_worker_pipeline_io(tmp_path) -> None:
    """With 4 workers, multiple fetches should be in-flight at once."""
    fetcher = _SlowOk(latency=0.05)
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    # 4 workers but only 20 req/s budget — that still allows 4 in flight.
    rl = RateLimiter(max_per_second=20.0, burst=20)

    qids = [f"Q{i}" for i in range(40)]
    t0 = time.time()
    out = fetch_sitelinks_resilient(
        qids,
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp,
        progress=lambda d, t: None,
        batch_size=2,
        max_workers=4,
    )
    elapsed = time.time() - t0
    cp.close()
    assert len(out) == 40
    # With 2s/req/worker serial = 2.0s for 40; 4-way parallel
    # should bring it well under 1.0s for 40 fetches.
    assert elapsed < 1.0
    # And we should have actually pipelined.
    assert fetcher.max_concurrent >= 2


def test_multi_worker_still_respects_rate_limiter(tmp_path) -> None:
    """Workers share the rate limiter — total throughput is bounded by it.

    With 20 batches at an 8 req/s budget we expect at least ~1.5s of
    wall time (after the initial burst of 8 tokens is consumed).  We
    don't pin the lower bound precisely because CI jitter can push
    the actual elapsed below the theoretical minimum by a few hundred
    milliseconds; we just assert it's clearly NOT sub-100ms (which
    would mean the rate limiter is broken).
    """
    fetcher = _SlowOk(latency=0.001)
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    # 8 req/s budget (well below worker count of 4).
    rl = RateLimiter(max_per_second=8.0, burst=8)

    qids = [f"Q{i}" for i in range(40)]
    t0 = time.time()
    out = fetch_sitelinks_resilient(
        qids,
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp,
        progress=lambda d, t: None,
        batch_size=2,
        max_workers=4,
    )
    elapsed = time.time() - t0
    cp.close()
    assert len(out) == 40
    # Sub-200ms would mean the rate limiter was bypassed.
    assert elapsed >= 0.2
    # And we should NOT have completed way faster than the budget
    # allows (20 batches / 8 per second ≈ 2.5s minimum).  Allow 50%
    # slack for thread coordination overhead.
    assert elapsed >= 1.0, (
        f"elapsed={elapsed:.2f}s suggests the rate limiter was bypassed"
    )


def test_multi_worker_handles_throttle_in_parallel(tmp_path) -> None:
    """Parallel workers all throttle → limiter halves multiple times."""
    fetcher = _Counting429(throttle_first=4)
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    rl = RateLimiter(max_per_second=10.0, burst=10)
    original = rl.max_per_second

    out = fetch_sitelinks_resilient(
        [f"Q{i}" for i in range(20)],
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp,
        progress=lambda d, t: None,
        batch_size=2,
        max_workers=3,
    )
    cp.close()
    assert len(out) == 20
    assert rl.max_per_second < original


def test_multi_worker_resumes_from_checkpoint(tmp_path) -> None:
    """Pre-populate the checkpoint, only the new QIDs should hit the API."""
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    cp.save("Q1", {"enwiki": {"title": "PRE"}})
    cp.save("Q2", {"enwiki": {"title": "PRE"}})
    cp.close()

    fetcher = _SlowOk(latency=0.001)
    cp2 = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    rl = RateLimiter(max_per_second=10_000.0, burst=10_000)
    out = fetch_sitelinks_resilient(
        ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"],
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp2,
        progress=lambda d, t: None,
        batch_size=2,
        max_workers=3,
    )
    cp2.close()
    assert out["Q1"]["enwiki"]["title"] == "PRE"
    assert out["Q3"]["enwiki"]["title"] == "T-Q3"
    # Fetcher only saw Q3..Q6 — no calls for Q1/Q2.
    assert all("Q1" not in c and "Q2" not in c for c in fetcher.calls)


def test_progress_fires_at_least_once_per_batch(tmp_path) -> None:
    """Progress is emitted as batches complete, regardless of worker count."""
    fetcher = _SlowOk(latency=0.001)
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    rl = RateLimiter(max_per_second=10_000.0, burst=10_000)
    seen: list[int] = []

    fetch_sitelinks_resilient(
        [f"Q{i}" for i in range(30)],
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp,
        progress=lambda d, t: seen.append(d),
        batch_size=2,
        max_workers=4,
    )
    cp.close()
    # 30 QIDs / 2 per batch = 15 batches → at least 15 progress events.
    assert len(seen) >= 15
    assert seen[-1] == 30
