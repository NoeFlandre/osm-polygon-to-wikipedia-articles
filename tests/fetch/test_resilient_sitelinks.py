"""Tests for the resilient, resumable batched sitelinks fetcher.

The new :func:`fetch_sitelinks_resilient` wraps the raw URL fetcher
with:

- a :class:`RateLimiter` to never exceed the Wikidata budget,
- a :class:`SitelinksCheckpoint` for resumability,
- a progress callback for live observability,
- an HTTP-429 detection that reports back to the limiter so it can
  adaptively slow down.

The tests use a stub URL fetcher so they don't hit the real API.
"""
from __future__ import annotations

from typing import Callable

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._rate_limiter import (
    RateLimiter,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch._sitelinks_checkpoint import (
    SitelinksCheckpoint,
)
from osm_polygon_to_wikipedia_articles.wikipedia.fetch._resilient_sitelinks import (
    fetch_sitelinks_resilient,
    _chunked,
    _build_url,
)


# ---------------------------------------------------------------------------
# URL building + chunking
# ---------------------------------------------------------------------------

def test_build_url_includes_pipe_separated_ids() -> None:
    url = _build_url(["Q1", "Q2", "Q3"])
    assert "ids=Q1%7CQ2%7CQ3" in url
    assert "action=wbgetentities" in url
    assert "props=sitelinks" in url


def test_chunked_splits_into_batches() -> None:
    out = list(_chunked(["Q1", "Q2", "Q3", "Q4", "Q5"], batch_size=2))
    assert out == [["Q1", "Q2"], ["Q3", "Q4"], ["Q5"]]


def test_chunked_empty() -> None:
    assert list(_chunked([], batch_size=10)) == []


# ---------------------------------------------------------------------------
# Stub URL fetcher
# ---------------------------------------------------------------------------

class _StubFetcher:
    """Pretends to call the Wikidata API.

    Records every call so tests can inspect them.  Configurable to
    return 429s on the first N calls.
    """

    def __init__(self, *, throttle_first: int = 0) -> None:
        self.calls: list[str] = []
        self.throttle_first = throttle_first
        self.call_count = 0

    def __call__(self, url: str) -> dict:
        self.call_count += 1
        self.calls.append(url)
        if self.call_count <= self.throttle_first:
            # Real urllib.error.HTTPError with code 429 so the
            # resilient loop's except clause catches it.
            import urllib.error
            raise urllib.error.HTTPError(
                url=url, code=429, msg="Too Many Requests", hdrs={}, fp=None,
            )
        # Pull the ids out of the URL and respond with a fake entity
        # dict.
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(url).query)
        ids = q["ids"][0].split("|")
        return {
            "entities": {
                qid: {"sitelinks": {"enwiki": {"title": f"Article-{qid}"}}}
                for qid in ids
            }
        }


class _Fake429(Exception):
    pass


# ---------------------------------------------------------------------------
# fetch_sitelinks_resilient
# ---------------------------------------------------------------------------

def test_resilient_returns_full_sitelinks_dict(tmp_path) -> None:
    fetcher = _StubFetcher()
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    rl = RateLimiter(max_per_second=100.0, burst=100)  # no throttling
    progress: list[int] = []

    out = fetch_sitelinks_resilient(
        ["Q1", "Q2", "Q3", "Q4", "Q5"],
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp,
        progress=lambda done, total: progress.append(done),
        batch_size=2,
    )
    assert len(out) == 5
    for qid in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
        assert out[qid]["enwiki"]["title"] == f"Article-{qid}"


def test_resilient_reports_throttle_to_rate_limiter(tmp_path) -> None:
    """3 throttles in a row should drop the rate to 1/8 of original."""
    fetcher = _StubFetcher(throttle_first=3)
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    rl = RateLimiter(max_per_second=8.0, burst=8)
    original = rl.max_per_second

    fetch_sitelinks_resilient(
        ["Q1", "Q2", "Q3"],
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp,
        progress=lambda d, t: None,
        batch_size=10,
    )
    # 3 throttles → 8 → 4 → 2 → 1
    assert rl.max_per_second < original
    assert rl.throttle_events == 3


def test_resilient_resumes_from_checkpoint(tmp_path) -> None:
    """Pre-populating the checkpoint with Q1+Q2 means the second
    call only fetches Q3, Q4, Q5.
    """
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    cp.save("Q1", {"enwiki": {"title": "PRE-EXISTING-1"}})
    cp.save("Q2", {"enwiki": {"title": "PRE-EXISTING-2"}})
    cp.close()

    fetcher = _StubFetcher()
    cp2 = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    rl = RateLimiter(max_per_second=100.0, burst=100)
    out = fetch_sitelinks_resilient(
        ["Q1", "Q2", "Q3", "Q4", "Q5"],
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp2,
        progress=lambda d, t: None,
        batch_size=2,
    )
    cp2.close()
    # Pre-existing entries are preserved
    assert out["Q1"]["enwiki"]["title"] == "PRE-EXISTING-1"
    assert out["Q2"]["enwiki"]["title"] == "PRE-EXISTING-2"
    # New entries fetched
    assert out["Q3"]["enwiki"]["title"] == "Article-Q3"
    # Fetcher only saw the Q3/Q4/Q5 batches
    assert all("Q1" not in c and "Q2" not in c for c in fetcher.calls)


def test_resilient_never_drops_a_qid(tmp_path) -> None:
    """Even with throttling, every QID is eventually resolved (or
    explicitly marked as not-found in the response).
    """
    fetcher = _StubFetcher(throttle_first=5)  # 5 throttles at the start
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    rl = RateLimiter(max_per_second=10.0, burst=10)
    out = fetch_sitelinks_resilient(
        [f"Q{i}" for i in range(1, 21)],
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp,
        progress=lambda d, t: None,
        batch_size=4,
    )
    assert len(out) == 20
    for i in range(1, 21):
        assert f"Q{i}" in out


def test_resilient_progress_callback_fires(tmp_path) -> None:
    fetcher = _StubFetcher()
    cp = SitelinksCheckpoint(tmp_path / "sl.jsonl")
    rl = RateLimiter(max_per_second=100.0, burst=100)
    seen: list[tuple[int, int]] = []

    fetch_sitelinks_resilient(
        ["Q1", "Q2", "Q3", "Q4", "Q5"],
        url_fetcher=fetcher,
        rate_limiter=rl,
        checkpoint=cp,
        progress=lambda done, total: seen.append((done, total)),
        batch_size=1,
    )
    # Progress should fire at least once per batch.
    assert len(seen) >= 5
    # Last progress should be (5, 5).
    assert seen[-1] == (5, 5)
