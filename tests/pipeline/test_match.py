"""Tests for the Wikidata matching orchestrator.

Network is fully stubbed via injected fetchers so the orchestrator stays
testable without HTTP.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.match import match_polygons
from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.types import ArticleSummary


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


def _stub_sitelinks(payload: dict[str, dict] | None):
    def fetch(qid: str):
        return payload
    return fetch


def _stub_summary(payload: ArticleSummary | None):
    def fetch(lang: str, title: str, **kwargs):
        return payload
    return fetch


def _stub_extract(body: str | None):
    def fetch(lang: str, title: str, **kwargs):
        return body
    return fetch


def test_match_returns_records_for_polygons_with_wikidata() -> None:
    df = _sample_df()

    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=_stub_sitelinks(SITELINKS_PORT_HERCULES),
        fetch_summary=_stub_summary(None),
        fetch_extract=_stub_extract(None),
    )
    assert len(results) == 1
    r = results[0]
    assert r.osm_id == 1
    assert r.wikidata_qid == "Q7230673"
    assert r.article_title == "Port Hercules"
    assert r.article_url == "https://en.wikipedia.org/wiki/Port_Hercules"
    assert r.match_status == "matched"


def test_match_records_no_qid_when_sitelinks_missing() -> None:
    df = _sample_df()

    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=_stub_sitelinks(None),
        fetch_summary=_stub_summary(None),
        fetch_extract=_stub_extract(None),
    )
    assert len(results) == 1
    assert results[0].match_status == "no_sitelinks"
    assert results[0].article_title is None


def test_match_records_no_lang_when_lang_not_in_sitelinks() -> None:
    df = _sample_df()

    results = match_polygons(
        df, lang="de",
        fetch_sitelinks=_stub_sitelinks(SITELINKS_PORT_HERCULES),
        fetch_summary=_stub_summary(None),
        fetch_extract=_stub_extract(None),
    )
    assert len(results) == 1
    assert results[0].match_status == "no_lang_sitelink"


def test_match_writes_jsonl(tmp_path: Path) -> None:
    df = _sample_df()
    out = tmp_path / "matches.jsonl"

    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=_stub_sitelinks(SITELINKS_PORT_HERCULES),
        fetch_summary=_stub_summary(None),
        fetch_extract=_stub_extract(None),
        out_jsonl=out,
    )

    assert out.exists()
    lines = out.read_text().strip().split("\n")
    assert len(lines) == len(results)
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

    def fetch(qid: str):
        pytest.fail("fetch should not be called when no polygons have wikidata")

    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=fetch,
        fetch_summary=_stub_summary(None),
        fetch_extract=_stub_extract(None),
    )
    assert results == []


def test_match_passes_through_geometry_wkt() -> None:
    """When the source df has geometry_wkt, it should flow into MatchResult."""
    df = pl.DataFrame({
        "osm_id": [1],
        "osm_type": ["way"],
        "centroid_lon": [1.5],
        "centroid_lat": [42.5],
        "tags": [["name=Foo", "wikidata=Q1"]],
        "country": ["andorra"],
        "size_bin": ["small"],
        "geometry_wkt": ["POLYGON((1 42, 2 42, 2 43, 1 43, 1 42))"],
    })

    def fetch(qid: str):
        return {"enwiki": {"title": "Foo"}}

    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=fetch,
        fetch_summary=_stub_summary(None),
        fetch_extract=_stub_extract(None),
    )
    assert len(results) == 1
    assert results[0].geometry_wkt == "POLYGON((1 42, 2 42, 2 43, 1 43, 1 42))"


def test_match_geometry_wkt_is_none_when_absent() -> None:
    """Older source dfs without geometry_wkt should not crash the orchestrator."""
    df = pl.DataFrame({
        "osm_id": [1],
        "osm_type": ["way"],
        "centroid_lon": [1.5],
        "centroid_lat": [42.5],
        "tags": [["wikidata=Q1"]],
        "country": ["andorra"],
        "size_bin": ["small"],
    })

    def fetch(qid: str):
        return {"enwiki": {"title": "Foo"}}

    results = match_polygons(
        df, lang="en",
        fetch_sitelinks=fetch,
        fetch_summary=_stub_summary(None),
        fetch_extract=_stub_extract(None),
    )
    assert results[0].geometry_wkt is None