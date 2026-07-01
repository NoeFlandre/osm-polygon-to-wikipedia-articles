"""Tests for the vectorised wikidata-tag extraction.

The source ``tags`` column is ``List[String]`` of ``"key=value"``
entries.  Some examples::

    ["name=Griffee Park", "leisure=park", "wikidata=Q12345"]
    ["operator:wikidata=Q206620", "name=Blanchardstown"]
    ["addr:city=Dublin"]

The extractor must:
- match **any** entry whose key starts with ``wikidata=`` (exact
  key, not substring — so ``wikipedia=Q42`` is NOT a match),
- return the value side (``Q12345``),
- ignore namespace prefixes like ``operator:wikidata=`` because
  those refer to *associated* entities (operator, subject, etc.),
  not the polygon itself.
"""
from __future__ import annotations

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.pipeline._wikidata_tags import (
    extract_wikidata_qids,
)


# ---------------------------------------------------------------------------
# Direct wikidata= key
# ---------------------------------------------------------------------------

def test_extracts_qid_from_direct_wikidata_tag() -> None:
    df = pl.DataFrame({
        "tags": [["name=Foo", "wikidata=Q42", "leisure=park"]],
    })
    out = extract_wikidata_qids(df, tags_col="tags")
    assert out["wikidata"][0] == "Q42"


def test_extracts_qid_when_wikidata_is_first_tag() -> None:
    df = pl.DataFrame({
        "tags": [["wikidata=Q99", "name=Bar"]],
    })
    out = extract_wikidata_qids(df, tags_col="tags")
    assert out["wikidata"][0] == "Q99"


# ---------------------------------------------------------------------------
# Namespace prefixes (must NOT be matched)
# ---------------------------------------------------------------------------

def test_does_not_match_namespaced_wikidata_tags() -> None:
    """Tags like ``operator:wikidata=Q206620`` refer to an associated
    entity, not the polygon itself.  We must not match them.
    """
    df = pl.DataFrame({
        "tags": [["operator:wikidata=Q206620", "name=Industrial Park"]],
    })
    out = extract_wikidata_qids(df, tags_col="tags")
    assert out["wikidata"][0] is None


def test_direct_wikidata_takes_precedence_over_namespaced() -> None:
    """When both ``wikidata=`` and ``operator:wikidata=`` are present,
    the direct one wins.
    """
    df = pl.DataFrame({
        "tags": [["operator:wikidata=Q206620", "wikidata=Q42", "name=Foo"]],
    })
    out = extract_wikidata_qids(df, tags_col="tags")
    assert out["wikidata"][0] == "Q42"


# ---------------------------------------------------------------------------
# No wikidata at all
# ---------------------------------------------------------------------------

def test_returns_none_when_no_wikidata_tag() -> None:
    df = pl.DataFrame({
        "tags": [["name=Foo", "leisure=park"], ["addr:city=Dublin"]],
    })
    out = extract_wikidata_qids(df, tags_col="tags")
    assert out["wikidata"].to_list() == [None, None]


def test_handles_null_tags_list() -> None:
    df = pl.DataFrame({
        "tags": [None, ["wikidata=Q42"], None],
    })
    out = extract_wikidata_qids(df, tags_col="tags")
    assert out["wikidata"].to_list() == [None, "Q42", None]


# ---------------------------------------------------------------------------
# Polars performance guard — must be vectorised, not Python iter_rows
# ---------------------------------------------------------------------------

def test_runs_on_50k_rows_under_one_second() -> None:
    """Sanity check that the implementation is vectorised.  50k rows
    of random tags should be processed in well under 1s on any
    reasonable machine; a per-row Python loop would take 5-30s.
    """
    import random
    import string
    random.seed(0)
    n = 50_000
    # 5% of rows have wikidata= at a random position
    tags_lists = []
    for _ in range(n):
        n_tags = random.randint(1, 5)
        tags = []
        if random.random() < 0.05:
            qid = "Q" + str(random.randint(1, 10_000_000))
            tags.append(f"wikidata={qid}")
        for _ in range(n_tags):
            tags.append(
                f"key{random.randint(0, 99)}=val{random.randint(0, 99)}"
            )
        random.shuffle(tags)
        tags_lists.append(tags)

    df = pl.DataFrame({"tags": tags_lists})
    import time as _time
    t0 = _time.time()
    out = extract_wikidata_qids(df, tags_col="tags")
    elapsed = _time.time() - t0
    # 50k rows × 1 wikidata match ~ 2,500 rows with QIDs
    n_with_qid = out["wikidata"].is_not_null().sum()
    assert 2_000 < n_with_qid < 3_000
    assert elapsed < 1.0, f"too slow: {elapsed:.2f}s (vectorisation broken?)"
