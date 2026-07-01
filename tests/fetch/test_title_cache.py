"""Tests for the per-title deduplication cache.

Many OSM polygons share the same Wikidata QID, and many QIDs map
to the same enwiki article (different QIDs for the same building,
or two polygons in the same park).  Without a cache, the pipeline
issues one HTTP request per (QID × lang × title), even though the
response is identical for duplicates.

``TitleCache`` turns ``fetch_summary(lang, title)`` and
``fetch_extract(lang, title)`` into memoised lookups: the first
caller does the network round-trip, every subsequent caller with
the same key gets the cached response.
"""
from __future__ import annotations

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._title_cache import (
    TitleCache,
)


# ---------------------------------------------------------------------------
# Basic memoisation
# ---------------------------------------------------------------------------

def test_caches_call_result_by_lang_title() -> None:
    call_count = {"n": 0}

    def fetcher(lang: str, title: str) -> dict | None:
        call_count["n"] += 1
        return {"title": title, "lang": lang}

    cache = TitleCache(fetcher=fetcher)
    a = cache.get("en", "Eiffel Tower")
    b = cache.get("en", "Eiffel Tower")
    assert a is b
    assert call_count["n"] == 1


def test_different_lang_is_a_different_key() -> None:
    call_count = {"n": 0}

    def fetcher(lang: str, title: str) -> dict | None:
        call_count["n"] += 1
        return {"lang": lang}

    cache = TitleCache(fetcher=fetcher)
    cache.get("en", "Eiffel Tower")
    cache.get("fr", "Tour Eiffel")
    assert call_count["n"] == 2


def test_different_title_is_a_different_key() -> None:
    call_count = {"n": 0}

    def fetcher(lang: str, title: str) -> dict | None:
        call_count["n"] += 1
        return {"title": title}

    cache = TitleCache(fetcher=fetcher)
    cache.get("en", "Eiffel Tower")
    cache.get("en", "Big Ben")
    assert call_count["n"] == 2


def test_none_result_is_NOT_cached() -> None:
    """A failed fetch (None) must NOT be cached — the next call must
    retry.  This is what allows the AdaptiveFetcher wrapper to do
    real work across multiple attempts (otherwise the second call
    just returns the cached None and no HTTP request is issued).
    """
    call_count = {"n": 0}

    def fetcher(lang: str, title: str) -> dict | None:
        call_count["n"] += 1
        return None

    cache = TitleCache(fetcher=fetcher)
    a = cache.get("en", "Eiffel Tower")
    b = cache.get("en", "Eiffel Tower")
    assert a is None
    assert b is None
    # Both calls should hit the fetcher (None isn't cached).
    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def test_hit_miss_counters() -> None:
    def fetcher(lang: str, title: str) -> dict | None:
        return {"ok": True}

    cache = TitleCache(fetcher=fetcher)
    cache.get("en", "A")  # miss
    cache.get("en", "A")  # hit
    cache.get("en", "A")  # hit
    cache.get("en", "B")  # miss
    cache.get("en", "B")  # hit
    stats = cache.stats()
    assert stats["hits"] == 3
    assert stats["misses"] == 2
    assert stats["size"] == 2


# ---------------------------------------------------------------------------
# Bulk prefetch
# ---------------------------------------------------------------------------

def test_prefetch_warms_cache_for_a_set_of_keys() -> None:
    """``prefetch`` issues one fetch per distinct (lang, title) and
    returns the count of network round-trips avoided downstream.
    """
    seen: list[tuple[str, str]] = []

    def fetcher(lang: str, title: str) -> dict | None:
        seen.append((lang, title))
        return {"title": title}

    cache = TitleCache(fetcher=fetcher)
    pairs = [
        ("en", "Eiffel Tower"),
        ("en", "Eiffel Tower"),  # duplicate
        ("en", "Big Ben"),
        ("fr", "Tour Eiffel"),
        ("en", "Big Ben"),  # duplicate
    ]
    n_fetched = cache.prefetch(pairs)
    assert n_fetched == 3  # 3 distinct (lang, title)
    assert len(seen) == 3


def test_prefetch_skips_already_cached_keys() -> None:
    call_count = {"n": 0}

    def fetcher(lang: str, title: str) -> dict | None:
        call_count["n"] += 1
        return {"ok": True}

    cache = TitleCache(fetcher=fetcher)
    cache.get("en", "Eiffel Tower")  # warms cache
    assert call_count["n"] == 1
    n_fetched = cache.prefetch([
        ("en", "Eiffel Tower"),  # already cached
        ("en", "Big Ben"),        # new
    ])
    assert n_fetched == 1
    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_cache_is_thread_safe_for_concurrent_gets() -> None:
    import threading
    call_count = {"n": 0}
    lock = threading.Lock()

    def fetcher(lang: str, title: str) -> dict | None:
        with lock:
            call_count["n"] += 1
        # Simulate slow HTTP
        import time as _time
        _time.sleep(0.01)
        return {"title": title}

    cache = TitleCache(fetcher=fetcher)
    results = []

    def worker():
        results.append(cache.get("en", "Eiffel Tower"))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All threads got the same value (correctness — even if multiple
    # fetches happened during the race window, every observer sees
    # the consistent value for that key).
    assert all(r == {"title": "Eiffel Tower"} for r in results)
    # Every result is the dict returned by the fetcher — never None,
    # never corrupted by concurrent writes.
    assert all(r is not None for r in results)
