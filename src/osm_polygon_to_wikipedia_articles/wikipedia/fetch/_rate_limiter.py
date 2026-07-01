"""Token-bucket rate limiter with adaptive back-off.

The Wikipedia / Wikidata anonymous rate limit is **5 req/s per IP**.
The naive approach — burst-fire requests, get blanket-throttled, sleep
30s, retry — wastes hours when running large batches.

This module provides a thread-safe token bucket that:

1. caps the request rate at a configurable ceiling (default 5 req/s),
2. allows a configurable burst (default = ceiling) so we can fire the
   first N requests immediately when we come back online,
3. **adaptively slows down** when a 429 is reported, halving the
   current rate each time, down to a hard floor of 0.5 req/s,
4. **gradually restores** the rate after sustained successes.

The bucket is process-shared via a lock so multiple worker threads
drawing from the same limiter never exceed the budget.
"""
from __future__ import annotations

import threading
import time
from typing import Optional


#: Hard floor on the adaptive rate — even on a heavily-throttled IP
#: we never slow below this so the pipeline always makes forward
#: progress.
MIN_RATE = 0.5


class RateLimiter:
    """Thread-safe token-bucket rate limiter with adaptive back-off.

    Parameters
    ----------
    max_per_second
        Initial (and maximum) request rate.  Defaults to 5.0 — the
        anonymous Wikidata / Wikipedia limit.
    burst
        Bucket size.  Defaults to ``max_per_second`` so the first
        N requests fire immediately.
    min_per_second
        Hard floor for the adaptive slow-down (default :data:`MIN_RATE`).
    time_fn
        Replacement for :func:`time.time` (injected for tests).
    sleep_fn
        Replacement for :func:`time.sleep` (injected for tests).
    """

    def __init__(
        self,
        max_per_second: float = 5.0,
        *,
        burst: Optional[float] = None,
        min_per_second: float = MIN_RATE,
        time_fn=time.time,
        sleep_fn=time.sleep,
    ) -> None:
        self._max = float(max_per_second)
        self._original_max = float(max_per_second)  # the ceiling we restore to
        self._burst = float(burst if burst is not None else max_per_second)
        self._min = float(min_per_second)
        self._time = time_fn
        self._sleep = sleep_fn
        self._tokens = self._burst
        self._last_refill = self._time()
        self._lock = threading.Lock()
        self.throttle_events = 0
        self.success_events = 0

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def max_per_second(self) -> float:
        """Current effective rate (drops on 429s, recovers on success)."""
        return self._max

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def acquire(self, blocking: bool = True) -> bool:
        """Wait for a token, then return True.

        If ``blocking=False`` and no token is available, return False
        immediately instead of sleeping.
        """
        while True:
            with self._lock:
                self._refill_locked()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                if not blocking:
                    return False
                # How long until 1 token is available at the current rate?
                wait_s = (1.0 - self._tokens) / self._max
            self._sleep(wait_s)
            # loop and try again

    def report_throttle(self) -> None:
        """Notify the limiter of a 429 / 5xx; halve the current rate.

        The rate is clamped at :data:`MIN_RATE` so a sustained throttle
        never stops us entirely.
        """
        with self._lock:
            self.throttle_events += 1
            new_rate = max(self._min, self._max / 2.0)
            self._max = new_rate
            # Drain the bucket so the next acquire waits for the new rate
            self._tokens = 0.0
            self._last_refill = self._time()

    def report_success(self) -> None:
        """Notify the limiter of a successful response; nudge the rate up.

        Each success adds ~5 % of the gap back to the original ceiling —
        so it takes ~20-30 consecutive successes to fully recover from a
        halving.  This prevents oscillation around the throttle
        threshold.
        """
        with self._lock:
            self.success_events += 1
            target = self._original_max
            if self._max < target:
                gap = target - self._max
                self._max = min(target, self._max + max(0.05, gap * 0.05))

    # ------------------------------------------------------------------
    # Debugging
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Return a JSON-serialisable snapshot for logging / metrics."""
        with self._lock:
            return {
                "max_per_second": round(self._max, 3),
                "min_per_second": self._min,
                "burst": self._burst,
                "tokens": round(self._tokens, 3),
                "throttle_events": self.throttle_events,
                "success_events": self.success_events,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refill_locked(self) -> None:
        """Refill the bucket based on elapsed time. Caller must hold lock."""
        now = self._time()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        refill = elapsed * self._max
        self._tokens = min(self._burst, self._tokens + refill)
        self._last_refill = now


__all__ = ["MIN_RATE", "RateLimiter"]
