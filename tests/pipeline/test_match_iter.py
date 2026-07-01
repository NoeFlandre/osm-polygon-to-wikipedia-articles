"""Tests for the match orchestrator's per-row iteration helper.

The old ``match_polygons`` had two near-identical branches (sequential
and concurrent) that both:

1. called ``_process_one`` per row,
2. filtered out ``None``,
3. wrote the result to the JSONL checkpoint.

This duplication is folded into :func:`iter_results`, which yields
``MatchResult`` instances in input order regardless of
``max_workers``. The tests below lock in the contract.
"""
from __future__ import annotations

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.match import (
    iter_results,
    _process_one,
)
from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.types import (
    ArticleSummary,
    MatchResult,
)


# ---------------------------------------------------------------------------
# Minimal stub fetchers
# ---------------------------------------------------------------------------

def _fake_sitelinks(qid: str) -> dict[str, dict[str, str]]:
    return {"enwiki": {"title": f"Article for {qid}"}}


def _fake_summary(lang: str, title: str) -> ArticleSummary:
    return ArticleSummary(
        title=title,
        description=f"desc for {title}",
        extract=f"extract of {title}",
        thumbnail_url=None,
        lat=None,
        lon=None,
        pageid=1,
        url=f"https://{lang}.wikipedia.org/wiki/{title}",
    )


def _fake_extract(lang: str, title: str) -> str:
    return f"body of {title}"


def _row(osm_id: int, qid: str) -> dict:
    return {
        "osm_id": osm_id,
        "osm_type": "way",
        "country": "italy",
        "size_bin": "small",
        "centroid_lon": 0.0,
        "centroid_lat": 0.0,
        "tags": [f"wikidata={qid}"],
    }


# ---------------------------------------------------------------------------
# Sequential mode
# ---------------------------------------------------------------------------

def test_iter_results_sequential_yields_one_per_row() -> None:
    rows = [_row(1, "Q1"), _row(2, "Q2"), _row(3, "Q3")]
    results = list(iter_results(rows, "en", _fake_sitelinks,
                                _fake_summary, _fake_extract,
                                max_workers=1))
    assert len(results) == 3
    assert [r.osm_id for r in results] == [1, 2, 3]


def test_iter_results_sequential_preserves_input_order() -> None:
    rows = [_row(99 - i, f"Q{i}") for i in range(5)]
    results = list(iter_results(rows, "en", _fake_sitelinks,
                                _fake_summary, _fake_extract,
                                max_workers=1))
    assert [r.osm_id for r in results] == [99, 98, 97, 96, 95]


# ---------------------------------------------------------------------------
# Concurrent mode
# ---------------------------------------------------------------------------

def test_iter_results_concurrent_yields_one_per_row() -> None:
    rows = [_row(i, f"Q{i}") for i in range(20)]
    results = list(iter_results(rows, "en", _fake_sitelinks,
                                _fake_summary, _fake_extract,
                                max_workers=4))
    assert len(results) == 20


def test_iter_results_concurrent_preserves_input_order() -> None:
    """Even under a thread pool, the output must be in input order."""
    rows = [_row(i, f"Q{i}") for i in range(50)]
    results = list(iter_results(rows, "en", _fake_sitelinks,
                                _fake_summary, _fake_extract,
                                max_workers=8))
    assert [r.osm_id for r in results] == list(range(50))


def test_iter_results_concurrent_with_max_workers_2() -> None:
    rows = [_row(i, f"Q{i}") for i in range(10)]
    results = list(iter_results(rows, "en", _fake_sitelinks,
                                _fake_summary, _fake_extract,
                                max_workers=2))
    assert [r.osm_id for r in results] == list(range(10))


# ---------------------------------------------------------------------------
# Empty / no-input cases
# ---------------------------------------------------------------------------

def test_iter_results_empty_input_yields_nothing() -> None:
    assert list(iter_results([], "en", _fake_sitelinks,
                             _fake_summary, _fake_extract,
                             max_workers=1)) == []
    assert list(iter_results([], "en", _fake_sitelinks,
                             _fake_summary, _fake_extract,
                             max_workers=4)) == []


# ---------------------------------------------------------------------------
# Dead-code removal regression guards
# ---------------------------------------------------------------------------

def test_module_does_not_define_dead_load_resume_keys() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.pipeline import match
    assert not hasattr(match, "_load_resume_keys"), (
        "_load_resume_keys was never called; remove it instead of carrying it."
    )


def test_module_does_not_define_dead_write_jsonl() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.pipeline import match
    assert not hasattr(match, "_write_jsonl"), (
        "_write_jsonl was never called; remove it instead of carrying it."
    )


# ---------------------------------------------------------------------------
# Real _process_one still works through the helper
# ---------------------------------------------------------------------------

def test_iter_results_returns_full_match_result() -> None:
    rows = [_row(1, "Q42")]
    [result] = list(iter_results(rows, "en", _fake_sitelinks,
                                 _fake_summary, _fake_extract,
                                 max_workers=1))
    assert isinstance(result, MatchResult)
    assert result.osm_id == 1
    assert result.wikidata_qid == "Q42"
    assert result.article_title == "Article for Q42"
    assert result.match_status == "matched"
    assert result.article_body_text == "body of Article for Q42"
