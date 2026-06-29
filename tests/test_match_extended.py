"""Tests for the extended match_polygons orchestrator.

The orchestrator now also fetches the Wikipedia summary + plain-text extract
for each matched polygon and writes a parquet (polygon fields + Wikidata + article fields).
All network calls are stubbed.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.match import match_polygons
from osm_polygon_to_wikipedia_articles.wikipedia.types import ArticleSummary


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame({
        "osm_id": [1, 2],
        "osm_type": ["way", "relation"],
        "centroid_lon": [9.5, 6.1],
        "centroid_lat": [47.2, 49.6],
        "tags": [
            ["name=Kihnu", "wikidata=Q1741199"],
            ["name=Foo", "wikidata=Q999"],
        ],
        "country": ["estonia", "luxembourg"],
        "size_bin": ["large", "small"],
    })


SITELINKS = {
    "Q1741199": {"enwiki": {"title": "Kihnu"}},
    "Q999": {"enwiki": {"title": "Foo"}},
}
SUMMARY_KIHNU = {
    "title": "Kihnu",
    "pageid": 12345,
    "description": "Island in Estonia",
    "extract": "Kihnu is an island in Estonia.",
    "thumbnail": {"source": "https://x/k.jpg"},
    "coordinates": {"lat": 58.13, "lon": 24.0},
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Kihnu"}},
}
SUMMARY_FOO = {
    "title": "Foo",
    "pageid": 7,
    "extract": "Foo.",
}
EXTRACT_KIHNU = "Kihnu is an island in the Baltic Sea..."
EXTRACT_FOO = "Foo bar baz."


def _to_summary(payload: dict) -> ArticleSummary:
    thumb = payload.get("thumbnail") or {}
    coords = payload.get("coordinates") or {}
    urls = (payload.get("content_urls") or {}).get("desktop") or {}
    return ArticleSummary(
        title=payload.get("title", ""),
        pageid=payload.get("pageid"),
        description=payload.get("description"),
        extract=payload.get("extract"),
        thumbnail_url=thumb.get("source"),
        lat=coords.get("lat"),
        lon=coords.get("lon"),
        url=urls.get("page"),
    )


def _stubs(summaries: dict[str, dict] | None = None, extracts: dict[str, str] | None = None):
    """Build (fetch_sitelinks, fetch_summary, fetch_extract) stubs from a map title->payload."""
    summaries = summaries or {}
    extracts = extracts or {}

    def fetch_sitelinks(qid: str):
        return SITELINKS[qid]

    def fetch_summary(lang: str, title: str, **kwargs):
        payload = summaries.get(title)
        return _to_summary(payload) if payload else None

    def fetch_extract(lang: str, title: str, **kwargs):
        return extracts.get(title)

    return fetch_sitelinks, fetch_summary, fetch_extract


def test_match_populates_summary_and_extract_fields() -> None:
    df = _sample_df()
    fsl, fs, fe = _stubs(
        summaries={"Kihnu": SUMMARY_KIHNU, "Foo": SUMMARY_FOO},
        extracts={"Kihnu": EXTRACT_KIHNU, "Foo": EXTRACT_FOO},
    )
    results = match_polygons(df, lang="en", fetch_sitelinks=fsl, fetch_summary=fs, fetch_extract=fe)
    assert len(results) == 2

    by_title = {r.article_title: r for r in results}
    kihnu = by_title["Kihnu"]
    assert kihnu.article_description == "Island in Estonia"
    assert kihnu.article_pageid == 12345
    assert kihnu.article_extract_short == "Kihnu is an island in Estonia."
    assert kihnu.article_body_text == EXTRACT_KIHNU
    assert kihnu.article_thumbnail_url == "https://x/k.jpg"
    assert kihnu.article_lat == 58.13
    assert kihnu.article_lon == 24.0
    assert kihnu.article_url == "https://en.wikipedia.org/wiki/Kihnu"


def test_match_handles_missing_summary_gracefully() -> None:
    df = _sample_df()
    fsl, fs, fe = _stubs()  # no summaries or extracts -> all None
    results = match_polygons(df, lang="en", fetch_sitelinks=fsl, fetch_summary=fs, fetch_extract=fe)
    assert all(r.article_title is not None for r in results)  # sitelink resolved
    assert all(r.article_description is None for r in results)
    assert all(r.article_body_text is None for r in results)


def test_match_writes_parquet(tmp_path: Path) -> None:
    df = _sample_df()
    out = tmp_path / "matches.parquet"
    fsl, fs, fe = _stubs(
        summaries={"Kihnu": SUMMARY_KIHNU, "Foo": SUMMARY_FOO},
        extracts={"Kihnu": EXTRACT_KIHNU, "Foo": EXTRACT_FOO},
    )
    match_polygons(df, lang="en", fetch_sitelinks=fsl, fetch_summary=fs, fetch_extract=fe, out_parquet=out)
    assert out.exists()

    written = pl.read_parquet(out)
    assert written.height == 2
    expected_cols = {
        "osm_id", "country", "wikidata_qid",
        "article_title", "article_description", "article_extract_short",
        "article_body_text", "article_thumbnail_url",
        "article_lat", "article_lon", "article_url", "article_pageid",
        "match_status",
    }
    assert expected_cols.issubset(set(written.columns))


def test_match_also_writes_jsonl(tmp_path: Path) -> None:
    df = _sample_df()
    out_jsonl = tmp_path / "matches.jsonl"
    fsl, fs, fe = _stubs(summaries={"Kihnu": SUMMARY_KIHNU, "Foo": SUMMARY_FOO})
    match_polygons(df, lang="en", fetch_sitelinks=fsl, fetch_summary=fs, fetch_extract=fe, out_jsonl=out_jsonl)
    lines = out_jsonl.read_text().strip().split("\n")
    assert len(lines) == 2
    import json
    rec = json.loads(lines[0])
    assert "article_body_text" in rec or "article_body_text" in json.loads(lines[1])
    assert any("article_body_text" in json.loads(l) for l in lines)