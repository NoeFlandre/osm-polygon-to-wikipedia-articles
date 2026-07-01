"""Per-title memoisation for Wikipedia summary/extract fetches.

Without this cache, the pipeline issues one HTTP request per
(QID × lang × title), even when many QIDs map to the same enwiki
article.  For a country like Italy (277k polygons, ~5 matched
articles), that's the difference between 5 fetches and 277 000.

The cache is intentionally simple:
- key = ``(lang, title)``
- value = the raw fetch result (dict or ``None``)
- thread-safe (lock around ``_cache`` dict)
- misses are still counted so the operator can see how much
  deduplication actually happened
"""
from __future__ import annotations

import threading
from typing import Callable, Iterable, Optional, Tuple

Fetcher = Callable[[str, str], Optional[dict]]


class TitleCache:
    """Memoised ``fetcher(lang, title)``.

    Parameters
    ----------
    fetcher
        The underlying fetch function (typically
        :func:`fetch_wikipedia_summary` or :func:`fetch_extract`).
    """

    def __init__(self, *, fetcher: Fetcher) -> None:
        self._fetcher = fetcher
        self._cache: dict[Tuple[str, str], Optional[dict]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Single get
    # ------------------------------------------------------------------

    def get(self, lang: str, title: str) -> Optional[dict]:
        """Return the cached value for ``(lang, title)`` or fetch it.

        ``None`` results are NOT cached — the next call retries.
        This lets callers wrap the cache in a retry loop (e.g.
        :class:`AdaptiveFetcher`) and have the retries actually
        reach the network instead of returning a cached None.
        """
        key = (lang, title)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._hits += 1
                return cached
        # Miss — fetch outside the lock so concurrent misses can
        # proceed in parallel.
        value = self._fetcher(lang, title)
        with self._lock:
            self._misses += 1
            if value is not None:
                self._cache[key] = value
            return value

    # ------------------------------------------------------------------
    # Bulk warm-up
    # ------------------------------------------------------------------

    def prefetch(self, pairs: Iterable[Tuple[str, str]]) -> int:
        """Warm the cache with a batch of ``(lang, title)`` pairs.

        Skips pairs that are already cached AND de-duplicates
        duplicates within the input itself.  Returns the number of
        network round-trips actually issued.
        """
        to_fetch: list[Tuple[str, str]] = []
        seen: set[Tuple[str, str]] = set()
        with self._lock:
            for pair in pairs:
                if pair in self._cache:
                    continue
                if pair in seen:
                    continue
                seen.add(pair)
                to_fetch.append(pair)
        for lang, title in to_fetch:
            self.get(lang, title)
        return len(to_fetch)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return ``{hits, misses, size}`` for logging."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
            }


__all__ = ["TitleCache"]
