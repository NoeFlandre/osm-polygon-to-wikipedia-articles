"""Adaptive retry wrapper for any HTTP-based fetcher.

The legacy ``_retry_forever`` helper in the rerun script used a
fixed exponential-backoff schedule with no awareness of the actual
rate-limit signal from the server.  On a sustained 429 it just
kept banging its head against the wall until it eventually gave
up (or worse, hit a 30-minute wall-clock stall).

``AdaptiveFetcher`` instead:
- delegates to a pluggable ``fn`` (typically
  :func:`fetch_summary` or :func:`fetch_extract`),
- acquires a token from a shared :class:`RateLimiter` before each
  attempt so we never exceed the API budget,
- on ``None`` (the fetch layer's universal "failed" signal) it
  reports a throttle to the limiter and waits for the limiter's
  recommended sleep (which grows when throttling is sustained),
- on success it reports success so the limiter can gradually
  restore its rate,
- stops after ``max_attempts`` and returns ``(None, attempts)``.

This keeps the "no silent drops" contract (every input ends up in
the result dict via the caller's status flag) while being much
friendlier to a throttled IP.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Tuple

from ._rate_limiter import RateLimiter


SleepFn = Callable[[float], None]


class AdaptiveFetcher:
    """Rate-limited, adaptive-retry wrapper around a single fetcher.

    Parameters
    ----------
    fn
        The underlying fetcher.  ``fn(*args, **kwargs)`` should
        return the article payload, or ``None`` if the request
        failed.
    rate_limiter
        Shared :class:`RateLimiter` for adaptive back-off.
    max_attempts
        Hard cap on retries (default 30 — enough to ride out
        multi-minute throttling without giving up too early).
    sleep
        Sleep function (injectable for tests).
    """

    def __init__(
        self,
        *,
        fn: Callable[..., Any],
        rate_limiter: RateLimiter,
        max_attempts: int = 30,
        sleep: Optional[SleepFn] = None,
    ) -> None:
        self._fn = fn
        self._rl = rate_limiter
        self._max_attempts = max_attempts
        if sleep is None:
            import time as _time
            self._sleep = _time.sleep
        else:
            self._sleep = sleep

    def run(self, *args, **kwargs) -> Tuple[Any, int]:
        """Call ``fn`` until it succeeds or ``max_attempts`` is hit.

        Returns ``(result, attempts)``.  ``result`` is whatever
        ``fn`` returned (possibly ``None`` if the cap was hit).
        """
        attempts = 0
        next_min_sleep = 1.0  # used as a floor when no rate hint
        while attempts < self._max_attempts:
            attempts += 1
            # Acquire a token — this is the single chokepoint that
            # ensures we never exceed the API budget, regardless of
            # how many other workers are also running.
            self._rl.acquire()
            try:
                result = self._fn(*args, **kwargs)
            except Exception:
                result = None
            if result is not None:
                self._rl.report_success()
                return result, attempts

            # Failure: report the throttle so the limiter halves.
            self._rl.report_throttle()
            if attempts >= self._max_attempts:
                break

            # Sleep based on the limiter's current state — when the
            # rate is halved, the limiter naturally wants longer
            # waits; when it's recovering, we sleep less.  Cap at
            # 30 s so we never block for absurd amounts of time.
            hint = self._rl.snapshot()
            target_per_s = max(hint["max_per_second"], 0.5)
            sleep_s = max(next_min_sleep, 1.0 / target_per_s)
            sleep_s = min(sleep_s, 30.0)
            self._sleep(sleep_s)
            # Exponential-ish floor in case the limiter stays stuck
            # at the floor (rare; keeps us from busy-looping on a
            # misconfigured IP).
            next_min_sleep = min(next_min_sleep * 1.5, 8.0)

        return None, attempts


__all__ = ["AdaptiveFetcher"]
