"""Tests for filtering _missing entries out of the checkpoint on load.

When a previous run failed (network outage, code bug, rate-limit
sustained for the full retry budget) the checkpoint ends up
containing only ``{"_missing": "..."}`` entries for the affected
QIDs.  On resume we want to re-attempt those QIDs instead of
serving stale "no sitelinks" answers to the caller.

The contract:
- ``load()`` filters out entries whose sitelinks dict contains a
  ``_missing`` key — they're treated as "not done" by the
  resilient layer and re-fetched.
- Successful entries (real sitelinks) are kept exactly as before.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._sitelinks_checkpoint import (
    SitelinksCheckpoint,
)


def test_load_skips_missing_entries(tmp_path: Path) -> None:
    """A checkpoint line with ``_missing`` must be filtered out so
    the resilient layer re-fetches the QID.
    """
    p = tmp_path / "sl.jsonl"
    p.write_text(
        '{"qid": "Q1", "sitelinks": {"enwiki": {"title": "OK1"}}}\n'
        '{"qid": "Q2", "sitelinks": {"_missing": "transient_failure"}}\n'
        '{"qid": "Q3", "sitelinks": {"enwiki": {"title": "OK3"}}}\n'
    )
    cp = SitelinksCheckpoint(p)
    out = cp.load()
    cp.close()
    # Q2 is filtered out — caller will re-fetch it.
    assert "Q1" in out
    assert "Q2" not in out
    assert "Q3" in out
    assert out["Q1"]["enwiki"]["title"] == "OK1"


def test_done_qids_excludes_filtered_missing(tmp_path: Path) -> None:
    p = tmp_path / "sl.jsonl"
    p.write_text(
        '{"qid": "Q1", "sitelinks": {"_missing": "transient_failure"}}\n'
        '{"qid": "Q2", "sitelinks": {"enwiki": {"title": "OK"}}}\n'
    )
    cp = SitelinksCheckpoint(p)
    cp.load()
    done = cp.done_qids()
    cp.close()
    assert done == {"Q2"}


def test_filter_pending_includes_missing_qids(tmp_path: Path) -> None:
    """``filter_pending`` should re-include QIDs whose checkpoint
    entry was ``_missing`` — they're not "done" from the caller's
    perspective.
    """
    p = tmp_path / "sl.jsonl"
    p.write_text(
        '{"qid": "Q1", "sitelinks": {"_missing": "x"}}\n'
        '{"qid": "Q2", "sitelinks": {"enwiki": {"title": "OK"}}}\n'
    )
    cp = SitelinksCheckpoint(p)
    pending = cp.filter_pending(["Q1", "Q2", "Q3"])
    cp.close()
    # Q1 is re-attempted, Q2 is skipped (done), Q3 is new.
    assert set(pending) == {"Q1", "Q3"}


def test_mixed_successful_and_missing_in_one_file(tmp_path: Path) -> None:
    """Sanity check: a checkpoint with both kinds of entries is
    loaded correctly.
    """
    p = tmp_path / "sl.jsonl"
    p.write_text(
        '{"qid": "Q1", "sitelinks": {"_missing": "http_503"}}\n'
        '{"qid": "Q2", "sitelinks": {"_missing": "throttled_10"}}\n'
        '{"qid": "Q3", "sitelinks": {"enwiki": {"title": "OK"}}}\n'
        '{"qid": "Q4", "sitelinks": {}}\n'  # empty sitelinks, NOT _missing
    )
    cp = SitelinksCheckpoint(p)
    out = cp.load()
    cp.close()
    # Q1, Q2 filtered (will be re-fetched); Q3, Q4 kept.
    assert "Q1" not in out
    assert "Q2" not in out
    assert "Q3" in out
    assert "Q4" in out
    # Q4 has empty sitelinks (no enwiki) — that's a real "no
    # sitelinks" answer, not a failure, so we keep it.
    assert out["Q4"] == {}
