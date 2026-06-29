"""Tests for the Wikidata matching orchestrator.

Network is fully stubbed via a ``fetch`` callable so the orchestrator stays
testable without HTTP.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.match import (
    MatchResult,
    match_polygons,
)


def _sample_df() -> pl.DataFrame:
    """Three polygons: one with a valid QID, one with a malformed one, one with none."""
    return pl.DataFrame({
        "osm_id": [1, 2, 3],
        "osm_type": ["way", "relation", "way"],
        "centroid_lon": [9.5, 6.1, -73.9],
        "centroid_lat": [47.2, 49.6, 40.7],
        "tags": [
            ["name=Port Hercules", "wikidata=Q7230673"],
            ["name=Foo", "wikidata=not-a-qid"],
            ["landuse=forest"],
        ],
        "country": ["monaco", "luxembourg", "estonia"],
        "size_bin": ["small", "large", "small"],
    })


SITELINKS_PORT_HERCULES = {
    "enwiki": {"title": "Port Hercules"},
    "frwiki": {"title": "Port Hercule"},
}


def test_match_returns_records_for_polygons_with_wikidata() -> None:
    df = _sample_df()

    def fetch(qid: str) -> dict | None:
        assert qid == "Q7230673"
        return SITELINKS_PORT_HERCULES

    results = match_polygons(df, lang="en", fetch=fetch)

    # Only one polygon has a valid wikidata= tag (id=1). The malformed one is filtered out by extract_wikidata_qid.
    assert len(results) == 1
    r = results[0]
    assert r.osm_id == 1
    assert r.wikidata_qid == "Q7230673"
    assert r.article_title == "Port Hercules"
    assert r.article_url == "https://en.wikipedia.org/wiki/Port_Hercules"
    assert r.match_status == "matched"


def test_match_records_no_qid_when_sitelinks_missing() -> None:
    df = _sample_df()

    def fetch(qid: str) -> dict | None:
        return None  # network / 404

    results = match_polygons(df, lang="en", fetch=fetch)
    assert len(results) == 1
    assert results[0].match_status == "no_sitelinks"
    assert results[0].article_title is None


def test_match_records_no_lang_when_lang_not_in_sitelinks() -> None:
    df = _sample_df()

    def fetch(qid: str) -> dict:
        return SITELINKS_PORT_HERCULES  # has en/fr but no de

    results = match_polygons(df, lang="de", fetch=fetch)
    assert len(results) == 1
    assert results[0].match_status == "no_lang_sitelink"


def test_match_writes_jsonl(tmp_path: Path) -> None:
    df = _sample_df()
    out = tmp_path / "matches.jsonl"

    def fetch(qid: str) -> dict:
        return SITELINKS_PORT_HERCULES

    results = match_polygons(df, lang="en", fetch=fetch, out_path=out)

    assert out.exists()
    lines = out.read_text().strip().split("\n")
    assert len(lines) == len(results)
    # JSON must be valid
    import json
    for line in lines:
        record = json.loads(line)
        assert "wikidata_qid" in record
        assert "match_status" in record


def test_match_empty_when_no_polygons_have_wikidata() -> None:
    df = pl.DataFrame({
        "osm_id": [1, 2],
        "osm_type": ["way", "way"],
        "centroid_lon": [0.0, 0.0],
        "centroid_lat": [0.0, 0.0],
        "tags": [["name=Foo"], ["landuse=forest"]],
        "country": ["x", "y"],
        "size_bin": ["small", "small"],
    })

    def fetch(qid: str) -> dict | None:
        pytest.fail("fetch should not be called when no polygons have wikidata")

    results = match_polygons(df, lang="en", fetch=fetch)
    assert results == []