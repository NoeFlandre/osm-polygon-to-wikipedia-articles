"""Tests for concurrent + resumable match_polygons.

Concurrency: when ``max_workers > 1``, fetch_sitelinks/fetch_summary/fetch_extract
are called concurrently (one thread per polygon). The set of qids/titles passed
in must still all be covered.

Resumability: when ``resume_jsonl`` points to an existing JSONL with prior
results, only polygons whose (osm_id, country) is NOT already in the file are
processed. Final JSONL = old results + new results, sorted by insertion order.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.match import match_polygons
from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.types import ArticleSummary


def _df(n: int) -> pl.DataFrame:
    """n polygons with a unique wikidata tag each."""
    rows = []
    for i in range(n):
        rows.append({
            "osm_id": i + 1,
            "osm_type": "way",
            "centroid_lon": 9.0 + i * 0.1,
            "centroid_lat": 47.0,
            "tags": [f"wikidata=Q{1000 + i}"],
            "country": "andorra",
            "size_bin": "small",
        })
    return pl.DataFrame(rows)


def _track_fetchers():
    """Fetchers that record every qid/title they see and what they return."""
    seen = {"sitelinks": [], "summary": [], "extract": []}
    lock = threading.Lock()

    def sitelinks(qid: str):
        with lock:
            seen["sitelinks"].append(qid)
        return {"enwiki": {"title": f"Article {qid}"}}

    def summary(lang: str, title: str, **kwargs):
        with lock:
            seen["summary"].append(title)
        return ArticleSummary(
            title=title, pageid=1, description="d", extract="e",
            thumbnail_url=None, lat=None, lon=None, url=None,
        )

    def extract(lang: str, title: str, **kwargs):
        with lock:
            seen["extract"].append(title)
        return f"body of {title}"

    return seen, sitelinks, summary, extract


def test_concurrent_runs_all_polygons() -> None:
    df = _df(20)
    seen, sitelinks, summary, extract = _track_fetchers()

    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=sitelinks,
        fetch_summary=summary,
        fetch_extract=extract,
        max_workers=4,
    )
    assert len(results) == 20
    # every qid seen exactly once
    assert sorted(seen["sitelinks"]) == sorted(f"Q{1000 + i}" for i in range(20))
    # every title resolved end-to-end
    for r in results:
        assert r.match_status == "matched"
        assert r.article_body_text.startswith("body of")


def test_concurrent_max_workers_one_is_sequential() -> None:
    df = _df(5)
    seen, sitelinks, summary, extract = _track_fetchers()
    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=sitelinks, fetch_summary=summary, fetch_extract=extract,
        max_workers=1,
    )
    assert len(results) == 5
    # max_workers=1 should still call everything exactly once
    assert sorted(seen["sitelinks"]) == sorted(f"Q{1000 + i}" for i in range(5))


def test_concurrent_results_sorted_by_input_order() -> None:
    df = _df(10)
    seen, sitelinks, summary, extract = _track_fetchers()
    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=sitelinks, fetch_summary=summary, fetch_extract=extract,
        max_workers=8,
    )
    assert [r.osm_id for r in results] == list(range(1, 11))


# --- resumability --------------------------------------------------------

def test_resume_skips_already_processed(tmp_path: Path) -> None:
    """If a prior run wrote some results to JSONL, only the missing polygons are fetched."""
    df = _df(10)
    resume_path = tmp_path / "prior.jsonl"

    # Seed prior results for osm_id 1..5
    prior = [
        {
            "osm_id": i + 1, "osm_type": "way", "country": "andorra",
            "size_bin": "small", "centroid_lon": 0.0, "centroid_lat": 0.0,
            "wikidata_qid": f"Q{1000 + i}",
            "article_title": f"Prior Article {i}",
            "article_lang": "en", "article_url": None, "sitelinks_count": 1,
            "match_status": "matched",
            "article_description": None, "article_extract_short": None,
            "article_thumbnail_url": None, "article_lat": None,
            "article_lon": None, "article_pageid": None,
            "article_body_text": f"prior body {i}", "geometry_wkt": None,
        }
        for i in range(5)
    ]
    resume_path.write_text("\n".join(json.dumps(r) for r in prior) + "\n")

    seen, sitelinks, summary, extract = _track_fetchers()
    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=sitelinks, fetch_summary=summary, fetch_extract=extract,
        max_workers=2,
        resume_jsonl=resume_path,
    )
    assert len(results) == 10
    # Only osm_id 6..10 should have triggered fetches
    assert sorted(seen["sitelinks"]) == [f"Q{1000 + i}" for i in range(5, 10)]
    # First 5 carry the prior results verbatim
    for i in range(5):
        r = results[i]
        assert r.osm_id == i + 1
        assert r.article_title == f"Prior Article {i}"
        assert r.article_body_text == f"prior body {i}"
    # Last 5 are freshly fetched
    for i in range(5, 10):
        r = results[i]
        assert r.osm_id == i + 1
        assert r.match_status == "matched"


def test_resume_writes_incremental_jsonl(tmp_path: Path) -> None:
    """During a run, JSONL should grow as polygons are processed (so a crash keeps progress)."""
    df = _df(30)
    out = tmp_path / "live.jsonl"
    seen, sitelinks, summary, extract = _track_fetchers()

    match_polygons(
        df, lang="en",
        fetch_sitelinks=sitelinks, fetch_summary=summary, fetch_extract=extract,
        max_workers=4,
        out_jsonl=out,
    )
    lines = [l for l in out.read_text().split("\n") if l.strip()]
    assert len(lines) == 30


def test_resume_no_prior_file_starts_from_scratch(tmp_path: Path) -> None:
    df = _df(3)
    resume_path = tmp_path / "missing.jsonl"
    assert not resume_path.exists()

    seen, sitelinks, summary, extract = _track_fetchers()
    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=sitelinks, fetch_summary=summary, fetch_extract=extract,
        max_workers=2,
        resume_jsonl=resume_path,
    )
    assert len(results) == 3
    assert sorted(seen["sitelinks"]) == ["Q1000", "Q1001", "Q1002"]
