"""Dataclasses shared across the wikipedia/ subpackage."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WikidataArticle:
    """A Wikipedia article resolved via a Wikidata QID."""
    qid: str
    lang: str
    title: str
    pageid: int | None  # Wikipedia pageid (resolved separately by lang/title)
    url: str


@dataclass(frozen=True)
class ArticleSummary:
    """Wikipedia REST summary payload, normalized."""
    title: str
    pageid: int | None
    description: str | None
    extract: str | None
    thumbnail_url: str | None
    lat: float | None
    lon: float | None
    url: str | None


@dataclass(frozen=True)
class MatchResult:
    """A polygon's full Wikipedia match outcome (sitelink + summary + body)."""
    # polygon identity
    osm_id: int
    osm_type: str
    country: str
    size_bin: str
    centroid_lon: float
    centroid_lat: float

    # Wikidata link
    wikidata_qid: str

    # sitelink resolution
    article_title: str | None
    article_lang: str | None
    article_url: str | None
    sitelinks_count: int
    match_status: str  # "matched" | "no_sitelinks" | "no_lang_sitelink"

    # REST summary
    article_description: str | None
    article_extract_short: str | None
    article_thumbnail_url: str | None
    article_lat: float | None
    article_lon: float | None
    article_pageid: int | None

    # full body (plain text)
    article_body_text: str | None

    # OSM polygon geometry (WKT, optional; populated when the source dataset
    # includes it). None when the polygon row didn't carry a geometry_wkt column.
    geometry_wkt: str | None