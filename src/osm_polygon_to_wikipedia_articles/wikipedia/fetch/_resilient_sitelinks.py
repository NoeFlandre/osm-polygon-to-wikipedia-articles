"""Resilient, rate-limit-aware, resumable batched sitelinks fetcher.

Combines:
- :class:`RateLimiter` (token bucket + adaptive 429 back-off)
- :class:`SitelinksCheckpoint` (JSONL side-channel for resumability)
- a pluggable ``url_fetcher`` (the production path is the existing
  :func:`get_json_with_retry`; tests inject a stub)

Design notes
------------
- The **rate limiter is the only thing that talks to the API**. Each
  ``acquire()`` blocks the worker until a token is available, so we
  never exceed the configured budget.
- On HTTP 429, the URL fetcher raises a :class:`urllib.error.HTTPError`
  with code 429 (or any 5xx). We catch it, call
  ``rate_limiter.report_throttle()`` (which halves the effective rate
  and drains the bucket), wait briefly, and retry — but **only as
  long as the rate limiter still has room to retry**. We do not loop
  forever here: a sustained throttle is reflected in the bucket
  size going to 0, which prevents further requests until the rate
  recovers.
- On any **other exception**, we record the QIDs as ``no_sitelinks``
  (with the exception class name in the dict for debugging) so the
  caller's "no silent drops" contract holds. They can be re-fetched
  on the next run if the underlying issue is transient.
- Successful responses are streamed into the checkpoint after every
  batch, so a SIGKILL at any point loses at most one in-flight batch.
"""
from __future__ import annotations

import threading
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable, Optional

from ._pooled_http_client import PooledHttpClient
from ._rate_limiter import RateLimiter
from ._sitelinks_checkpoint import SitelinksCheckpoint


WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def _build_url(qids: list[str]) -> str:
    """Build the ``wbgetentities`` URL for a batch of QIDs."""
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "sitelinks",
        "format": "json",
    }
    return WIKIDATA_API + "?" + urllib.parse.urlencode(params)


def _chunked(items: list, batch_size: int) -> Iterable[list]:
    """Yield ``items`` in chunks of ``batch_size``."""
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


# Default URL fetcher: shared PooledHttpClient.  Thread-safe, keeps
# connections warm (huge speedup vs. urllib.request.urlopen which
# opens a fresh TCP/TLS connection for every request), and optionally
# negotiates HTTP/2 for multiplexing.
_default_client: Optional[PooledHttpClient] = None
_default_client_lock = threading.Lock()


def _get_default_client() -> PooledHttpClient:
    """Return a process-shared pooled client (created lazily)."""
    global _default_client
    if _default_client is not None:
        return _default_client
    with _default_client_lock:
        if _default_client is None:
            _default_client = PooledHttpClient()
    return _default_client


def _default_url_fetcher(url: str) -> dict:
    client = _get_default_client()
    payload = client.get_json(url)
    if payload is None:
        # The pooled client already retried — surface as a transient
        # failure so the resilient loop can decide whether to record
        # the batch as missing or wait for the rate limiter to recover.
        raise _TransientFailure("PooledHttpClient.get_json returned None")
    return payload


class _TransientFailure(Exception):
    """Raised when the underlying fetcher gives up after retries."""


#: Type alias for the progress callback.  ``done`` is the number of
#: QIDs already in the result dict, ``total`` is the total expected.
ProgressFn = Callable[[int, int], None]


def fetch_sitelinks_resilient(
    qids: list[str],
    *,
    url_fetcher: Callable[[str], dict] = _default_url_fetcher,
    rate_limiter: Optional[RateLimiter] = None,
    checkpoint: Optional[SitelinksCheckpoint] = None,
    progress: Optional[ProgressFn] = None,
    batch_size: int = 50,
    max_consecutive_failures: int = 10,
    max_workers: int = 1,
) -> dict[str, dict]:
    """Fetch sitelinks for many QIDs, rate-limited, resumable.

    Parameters
    ----------
    qids
        All QIDs we eventually want sitelinks for.
    url_fetcher
        Pluggable HTTP GET.  Default is the production
        :func:`get_json_with_retry`; tests pass a stub.
    rate_limiter
        Optional shared rate limiter.  Defaults to a 5 req/s limiter
        (the Wikidata anonymous budget).
    checkpoint
        Optional JSONL checkpoint for resumability.  Defaults to an
        in-memory only checkpoint (no on-disk persistence).
    progress
        Optional callback ``(done, total)`` invoked after each batch.
    batch_size
        QIDs per ``wbgetentities`` request.  Default 50 — the upper
        limit the Wikidata API accepts.
    max_consecutive_failures
        Give up on a batch after this many consecutive 429s and
        record the QIDs as no_sitelinks.  The rate limiter has
        already halved on each 429, so this is the safety valve
        for a persistently broken IP.
    max_workers
        Number of parallel fetch workers.  All workers share the
        same ``rate_limiter`` so the total throughput is bounded
        by the configured rate budget — workers just pipeline the
        I/O so the bucket doesn't sit idle.  ``1`` = serial.

    Returns
    -------
    ``{qid: sitelinks_dict}`` for every QID.  QIDs that could not
    be fetched appear with value ``{"_missing": "<reason>"}`` so the
    caller can distinguish "no enwiki sitelink" from "we couldn't
    reach the API".
    """
    if not qids:
        return {}
    rl = rate_limiter or RateLimiter()
    cp = checkpoint or SitelinksCheckpoint(_InMemoryPath())  # type: ignore

    # Pre-load checkpoint into memory; merge the saved QIDs into the
    # result dict so the caller sees the union of (checkpoint) and
    # (new fetches).
    cp.load()
    out: dict[str, dict] = {qid: sl for qid, sl in cp._in_memory.items()}
    pending = cp.filter_pending(qids)
    total = len(qids)
    if progress:
        progress(len(out), total)

    # Lock guarding shared mutation of ``out`` and ``cp``.
    out_lock = threading.Lock()

    def _process_batch(batch: list[str]) -> None:
        """Fetch one batch, handling retries + transient failures."""
        url = _build_url(batch)
        consecutive = 0
        while True:
            rl.acquire()
            try:
                payload = url_fetcher(url)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504):
                    rl.report_throttle()
                    consecutive += 1
                    if consecutive >= max_consecutive_failures:
                        # Give up on this batch — record as missing
                        # and move on so the whole run doesn't stall.
                        with out_lock:
                            for qid in batch:
                                out[qid] = {"_missing": f"throttled_{consecutive}"}
                                cp.save(qid, out[qid])
                        break
                    # Pause briefly so we don't busy-loop on 429s.
                    rl.acquire()
                    continue
                # Permanent 4xx (other than 429) → record and move on
                with out_lock:
                    for qid in batch:
                        out[qid] = {"_missing": f"http_{e.code}"}
                        cp.save(qid, out[qid])
                break
            except _TransientFailure:
                rl.report_throttle()
                consecutive += 1
                if consecutive >= max_consecutive_failures:
                    with out_lock:
                        for qid in batch:
                            out[qid] = {"_missing": "transient_failure"}
                            cp.save(qid, out[qid])
                    break
                continue
            except Exception as e:
                with out_lock:
                    for qid in batch:
                        out[qid] = {"_missing": f"error_{type(e).__name__}"}
                        cp.save(qid, out[qid])
                break

            # Success: extract entities, save to checkpoint, advance.
            entities = payload.get("entities", {})
            with out_lock:
                for qid in batch:
                    ent = entities.get(qid)
                    if not ent or ent.get("missing"):
                        # Truly no entity → not a failure, just no sitelinks
                        out[qid] = {"_missing": "no_entity"}
                    else:
                        out[qid] = ent.get("sitelinks", {})
                    cp.save(qid, out[qid])
            rl.report_success()
            break

    # Dispatch batches across workers.  ``as_completed`` lets us
    # emit progress as soon as each batch finishes instead of waiting
    # for all batches at the end.
    if max_workers <= 1:
        for batch in _chunked(pending, batch_size):
            _process_batch(batch)
            if progress:
                progress(len(out), total)
    else:
        batches = list(_chunked(pending, batch_size))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_process_batch, b): b for b in batches}
            for fut in as_completed(futures):
                # Surface any unhandled exception from the worker.
                fut.result()
                if progress:
                    progress(len(out), total)

    return out


class _InMemoryPath:
    """Drop-in for ``pathlib.Path`` that stores in memory only.

    Used when no checkpoint path is supplied.  SitelinksCheckpoint
    only calls ``mkdir(parents=True, exist_ok=True)`` and
    ``path.open(...)`` and ``path.stat()`` and ``path.exists()``,
    so we provide a stub.
    """
    name = "<in-memory>"

    def __init__(self) -> None:
        self._data: str = ""

    @property
    def parent(self) -> "_InMemoryDir":
        return _InMemoryDir()

    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        return None

    def exists(self) -> bool:
        return False

    def stat(self) -> "_InMemoryStat":
        return _InMemoryStat(0)

    def open(self, mode: str = "r", buffering: int = -1):  # type: ignore
        import io
        return io.StringIO()


class _InMemoryDir:
    def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
        return None


class _InMemoryStat:
    def __init__(self, size: int) -> None:
        self.st_size = size


__all__ = [
    "WIKIDATA_API",
    "fetch_sitelinks_resilient",
    "_build_url",
    "_chunked",
]
