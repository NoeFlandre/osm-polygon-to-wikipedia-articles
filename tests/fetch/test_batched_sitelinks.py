"""Tests for the batched Wikidata sitelinks fetcher.

Batched fetch lets us trade N round-trips for ~N/50 round-trips by piping
QIDs into ``wbgetentities``. The expected behaviour: every QID that comes
back as an entity gets a sitelinks sub-dict, missing entities are silently
omitted, and the API is queried in batches of ``batch_size``.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from osm_polygon_to_wikipedia_articles.wikipedia.fetch.batched_sitelinks import (
    fetch_sitelinks_batched,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _fake_urlopen_for(qid_to_payload):
    """Build a fake ``urlopen`` callable.

    The retry layer invokes ``urlopen(req, timeout=...)`` where ``req`` is
    a ``urllib.request.Request``. We extract the URL from it and look up
    the corresponding fake response payload.
    """
    def fake_urlopen(req, timeout=20):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        # Find QIDs in the URL: ids= param is pipe-separated
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        qparams = urllib.parse.parse_qs(parsed.query)
        ids = qparams.get("ids", [""])[0].split("|")
        entities = {q: qid_to_payload.get(q, {"sitelinks": {}}) for q in ids}
        return FakeResponse({"entities": entities})
    return fake_urlopen


def test_empty_input_returns_empty_dict():
    out = fetch_sitelinks_batched([], urlopen=MagicMock(), sleep=lambda _s: None)
    assert out == {}


def test_single_batch_returns_sitelinks_per_qid():
    qids = ["Q1", "Q2"]
    qid_to_payload = {
        "Q1": {"sitelinks": {"enwiki": {"title": "Foo"}}},
        "Q2": {"sitelinks": {"enwiki": {"title": "Bar"}}},
    }
    out = fetch_sitelinks_batched(
        qids, urlopen=_fake_urlopen_for(qid_to_payload), sleep=lambda _s: None
    )
    assert set(out.keys()) == {"Q1", "Q2"}
    assert out["Q1"]["enwiki"]["title"] == "Foo"
    assert out["Q2"]["enwiki"]["title"] == "Bar"


def test_batching_groups_qids_in_chunks_of_batch_size():
    qids = [f"Q{i}" for i in range(120)]
    qid_to_payload = {q: {"sitelinks": {"enwiki": {"title": q}}} for q in qids}
    captured_urls = []

    def fake_urlopen(req, timeout=20):
        url = req.full_url
        captured_urls.append(url)
        return _fake_urlopen_for(qid_to_payload)(req, timeout)

    fetch_sitelinks_batched(
        qids, batch_size=50, urlopen=fake_urlopen, sleep=lambda _s: None
    )
    # 120 qids with batch_size 50 → 3 batches
    assert len(captured_urls) == 3
    # First batch: Q0..Q49
    assert all(f"Q{i}" in captured_urls[0] for i in range(50))
    # Second batch: Q50..Q99
    assert all(f"Q{i}" in captured_urls[1] for i in range(50, 100))
    # Third batch: Q100..Q119
    assert all(f"Q{i}" in captured_urls[2] for i in range(100, 120))


def test_missing_entities_are_omitted():
    qids = ["Q1", "Q2", "Q3"]
    qid_to_payload = {
        "Q1": {"sitelinks": {"enwiki": {"title": "Foo"}}},
        "Q2": {"missing": True},
        "Q3": None,
    }
    out = fetch_sitelinks_batched(
        qids, urlopen=_fake_urlopen_for(qid_to_payload), sleep=lambda _s: None
    )
    assert set(out.keys()) == {"Q1"}


def test_429_handled_by_retry_layer_does_not_silently_drop_qids():
    """If the underlying fetcher returns None (after all retries), the
    resilient layer must NOT silently skip the QIDs — it records them
    as ``{"_missing": "transient_failure"}`` so the caller can see
    every QID was attempted.  This is the regression guard for the
    "no silent drops" contract.
    """
    from osm_polygon_to_wikipedia_articles.wikipedia.fetch._resilient_sitelinks import (
        fetch_sitelinks_resilient,
        _TransientFailure,
    )
    from osm_polygon_to_wikipedia_articles.wikipedia.fetch._rate_limiter import (
        RateLimiter,
    )
    from osm_polygon_to_wikipedia_articles.wikipedia.fetch._sitelinks_checkpoint import (
        SitelinksCheckpoint,
    )

    qids = [f"Q{i}" for i in range(10)]
    failing_qids = {"Q5", "Q6", "Q7", "Q8", "Q9"}
    call_count = {"n": 0}

    def fake_fetcher(url: str) -> dict:
        call_count["n"] += 1
        # The second batch (Q5..Q9) keeps failing — surface as transient
        # so the resilient loop records _missing instead of dropping.
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        qparams = urllib.parse.parse_qs(parsed.query)
        batch_qids = qparams.get("ids", [""])[0].split("|")
        if any(q in failing_qids for q in batch_qids):
            raise _TransientFailure("simulated permanent failure")
        return {
            "entities": {
                q: {"sitelinks": {"enwiki": {"title": q}}}
                for q in batch_qids
            }
        }

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        cp = SitelinksCheckpoint(tmp + "/sl.jsonl")
        rl = RateLimiter(max_per_second=1000, burst=1000)
        out = fetch_sitelinks_resilient(
            qids,
            url_fetcher=fake_fetcher,
            rate_limiter=rl,
            checkpoint=cp,
            progress=lambda d, t: None,
            batch_size=5,
            max_consecutive_failures=2,
        )
        cp.close()
    # Every QID must be in the result — the failing batch's QIDs are
    # marked _missing, not dropped.
    assert len(out) == 10
    assert all(qid in out for qid in qids)
    # 5 from the successful batch + 5 _missing from the failed one
    missing = [qid for qid, sl in out.items() if "_missing" in sl]
    assert len(missing) == 5
    assert all(qid in failing_qids for qid in missing)


def test_sleep_is_called_between_batches():
    sleep_calls = []
    qids = [f"Q{i}" for i in range(120)]
    qid_to_payload = {q: {"sitelinks": {}} for q in qids}
    fetch_sitelinks_batched(
        qids,
        batch_size=50,
        urlopen=_fake_urlopen_for(qid_to_payload),
        sleep=sleep_calls.append,
    )
    # 3 batches → 3 sleeps in current implementation
    assert len(sleep_calls) == 3
