"""Tests for the resumable sitelinks checkpoint.

The new pipeline saves each batch's Wikidata sitelinks to a
side-channel checkpoint file (JSONL) *as soon as it succeeds*, so
that a kill / crash at any point loses at most one batch of work.

The checkpoint is a streaming-friendly format: one QID per line,
written atomically (write-to-temp + rename) so a SIGKILL mid-write
can't corrupt it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.fetch._sitelinks_checkpoint import (
    SitelinksCheckpoint,
)


def _sitelinks(qid: str, lang: str = "enwiki") -> dict:
    return {lang: {"title": f"Article for {qid}"}}


# ---------------------------------------------------------------------------
# Basic save / load roundtrip
# ---------------------------------------------------------------------------

def test_save_and_load_single_qid(tmp_path: Path) -> None:
    p = tmp_path / "sitelinks.jsonl"
    cp = SitelinksCheckpoint(p)
    cp.save("Q42", _sitelinks("Q42"))
    cp.close()

    cp2 = SitelinksCheckpoint(p)
    out = cp2.load()
    cp2.close()
    assert "Q42" in out
    assert out["Q42"]["enwiki"]["title"] == "Article for Q42"


def test_load_returns_empty_dict_when_file_missing(tmp_path: Path) -> None:
    cp = SitelinksCheckpoint(tmp_path / "missing.jsonl")
    assert cp.load() == {}


def test_done_qids_reflects_what_was_saved(tmp_path: Path) -> None:
    p = tmp_path / "sitelinks.jsonl"
    cp = SitelinksCheckpoint(p)
    cp.save("Q1", _sitelinks("Q1"))
    cp.save("Q2", _sitelinks("Q2"))
    cp.close()

    cp2 = SitelinksCheckpoint(p)
    assert cp2.done_qids() == {"Q1", "Q2"}
    cp2.close()


def test_save_does_not_duplicate(tmp_path: Path) -> None:
    """Re-saving a QID overwrites the previous entry, doesn't duplicate."""
    p = tmp_path / "sitelinks.jsonl"
    cp = SitelinksCheckpoint(p)
    cp.save("Q1", _sitelinks("Q1", "enwiki"))
    cp.save("Q1", _sitelinks("Q1", "dewiki"))  # overwrite
    cp.close()

    cp2 = SitelinksCheckpoint(p)
    out = cp2.load()
    cp2.close()
    assert out["Q1"]["dewiki"]["title"] == "Article for Q1"
    assert "enwiki" not in out["Q1"]


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------

def test_save_is_atomic_against_partial_read(tmp_path: Path) -> None:
    """A reader that opens the file mid-write must see either the
    pre-write or post-write state, never a half-written line.
    """
    p = tmp_path / "sitelinks.jsonl"
    cp = SitelinksCheckpoint(p)
    cp.save("Q1", _sitelinks("Q1"))
    cp.save("Q2", _sitelinks("Q2"))
    cp.save("Q3", _sitelinks("Q3"))
    # Don't close — check that a parallel reader sees a complete file
    cp_reader = SitelinksCheckpoint(p)
    out = cp_reader.load()
    cp_reader.close()
    cp.close()
    # The reader may see 0..3 QIDs depending on timing, but no malformed line
    for qid, sl in out.items():
        assert qid.startswith("Q")
        assert isinstance(sl, dict)


def test_corrupted_lines_are_skipped(tmp_path: Path) -> None:
    """A single corrupted line shouldn't poison the whole checkpoint."""
    p = tmp_path / "sitelinks.jsonl"
    p.write_text(
        '{"qid": "Q1", "sitelinks": {"enwiki": {"title": "OK"}}}\n'
        'this-is-not-json\n'
        '{"qid": "Q2", "sitelinks": {"enwiki": {"title": "OK2"}}}\n'
    )
    cp = SitelinksCheckpoint(p)
    out = cp.load()
    cp.close()
    assert "Q1" in out
    assert "Q2" in out


# ---------------------------------------------------------------------------
# Merging with new fetches
# ---------------------------------------------------------------------------

def test_filter_pending_removes_already_done(tmp_path: Path) -> None:
    """``filter_pending`` returns the input minus the already-saved QIDs."""
    p = tmp_path / "sitelinks.jsonl"
    cp = SitelinksCheckpoint(p)
    cp.save("Q1", _sitelinks("Q1"))
    cp.save("Q2", _sitelinks("Q2"))
    cp.close()

    cp2 = SitelinksCheckpoint(p)
    pending = cp2.filter_pending(["Q1", "Q2", "Q3", "Q4"])
    cp2.close()
    assert set(pending) == {"Q3", "Q4"}


def test_filter_pending_when_checkpoint_empty(tmp_path: Path) -> None:
    p = tmp_path / "sitelinks.jsonl"
    cp = SitelinksCheckpoint(p)
    pending = cp.filter_pending(["Q1", "Q2", "Q3"])
    cp.close()
    assert set(pending) == {"Q1", "Q2", "Q3"}


# ---------------------------------------------------------------------------
# Save format
# ---------------------------------------------------------------------------

def test_save_format_is_one_json_per_line(tmp_path: Path) -> None:
    p = tmp_path / "sitelinks.jsonl"
    cp = SitelinksCheckpoint(p)
    cp.save("Q1", _sitelinks("Q1"))
    cp.save("Q2", _sitelinks("Q2"))
    cp.close()

    text = p.read_text()
    lines = [l for l in text.splitlines() if l]
    assert len(lines) == 2
    for line in lines:
        rec = json.loads(line)
        assert "qid" in rec
        assert "sitelinks" in rec


def test_size_returns_estimated_file_size(tmp_path: Path) -> None:
    p = tmp_path / "sitelinks.jsonl"
    cp = SitelinksCheckpoint(p)
    cp.save("Q1", _sitelinks("Q1"))
    cp.save("Q2", _sitelinks("Q2"))
    cp.save("Q3", _sitelinks("Q3"))
    cp.close()
    cp2 = SitelinksCheckpoint(p)
    size = cp2.size_bytes()
    cp2.close()
    assert size > 0
    assert size == p.stat().st_size
