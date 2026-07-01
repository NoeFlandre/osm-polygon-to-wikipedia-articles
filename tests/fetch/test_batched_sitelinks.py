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


def test_returns_none_on_429_handled_by_retry_layer():
    """If ``get_json_with_retry`` returns None (after all retries), the
    QIDs in that batch are silently skipped — we return whatever we got
    from the other batches.
    """
    qids = [f"Q{i}" for i in range(10)]
    call_count = {"n": 0}

    def fake_get_json_with_retry(url, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            return None  # Second batch failed entirely
        import urllib.parse
        parsed = urllib.parse.urlparse(url)
        qparams = urllib.parse.parse_qs(parsed.query)
        batch_qids = qparams.get("ids", [""])[0].split("|")
        return {
            "entities": {
                q: {"sitelinks": {"enwiki": {"title": q}}}
                for q in batch_qids
            }
        }

    with patch(
        "osm_polygon_to_wikipedia_articles.wikipedia.fetch.batched_sitelinks.get_json_with_retry",
        side_effect=fake_get_json_with_retry,
    ):
        out = fetch_sitelinks_batched(qids, batch_size=5, sleep=lambda _s: None)

    # 2 batches total, 1 succeeded (5 qids) and 1 returned None (5 qids missed)
    assert len(out) == 5
    assert call_count["n"] == 2
    # All returned QIDs are from the first batch (Q0..Q4)
    assert all(qid.startswith("Q") and int(qid[1:]) < 5 for qid in out.keys())


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
