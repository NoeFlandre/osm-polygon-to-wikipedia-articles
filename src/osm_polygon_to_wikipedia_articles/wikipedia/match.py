"""Orchestrator: walk a polygon sample, fetch Wikidata + Wikipedia article data.

Pure composition over ``wikidata.py``, ``summary.py``, ``extracts.py``. Network
access is injected via ``fetch_sitelinks``, ``fetch_summary``, ``fetch_extract``
so tests can stub it.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Protocol

import polars as pl

from .wikidata import (
    extract_wikidata_qid,
    filter_polygons_with_wikidata,
    resolve_wikidata_to_article,
)
from .types import MatchResult, ArticleSummary


class SitelinksFetcher(Protocol):
    def __call__(self, qid: str) -> dict[str, dict[str, str]] | None: ...


class SummaryFetcher(Protocol):
    def __call__(self, lang: str, title: str) -> ArticleSummary | None: ...


class ExtractFetcher(Protocol):
    def __call__(self, lang: str, title: str) -> str | None: ...


def match_polygons(
    df: pl.DataFrame,
    lang: str = "en",
    *,
    fetch_sitelinks: SitelinksFetcher | None = None,
    fetch_summary: SummaryFetcher | None = None,
    fetch_extract: ExtractFetcher | None = None,
    out_parquet: Path | None = None,
    out_jsonl: Path | None = None,
) -> list[MatchResult]:
    """For every polygon with a valid ``wikidata=*`` tag:

    1. resolve to the Wikipedia article title via Wikidata sitelinks
    2. fetch the REST summary (extract, description, thumbnail, coords, pageid, url)
    3. fetch the plain-text body of the article
    """
    fetch_sitelinks = fetch_sitelinks or _stub_fetch_sitelinks
    fetch_summary = fetch_summary or _stub_fetch_summary
    fetch_extract = fetch_extract or _stub_fetch_extract

    wd_df = filter_polygons_with_wikidata(df)
    has_geom = "geometry_wkt" in df.columns
    results: list[MatchResult] = []

    for row in wd_df.iter_rows(named=True):
        qid = extract_wikidata_qid(row["tags"])
        if qid is None:
            continue

        sitelinks = fetch_sitelinks(qid) or {}
        article = resolve_wikidata_to_article(qid, lang=lang, sitelinks=sitelinks)

        if not sitelinks:
            status = "no_sitelinks"
        elif article is None:
            status = "no_lang_sitelink"
        else:
            status = "matched"

        # summary + body (best-effort; None on failure)
        summary_obj: ArticleSummary | None = None
        body: str | None = None
        if article is not None:
            summary_obj = fetch_summary(lang, article.title)
            body = fetch_extract(lang, article.title)

        results.append(MatchResult(
            osm_id=row["osm_id"],
            osm_type=row["osm_type"],
            country=row["country"],
            size_bin=row["size_bin"],
            centroid_lon=row["centroid_lon"],
            centroid_lat=row["centroid_lat"],
            wikidata_qid=qid,
            article_title=article.title if article else None,
            article_lang=lang if article else None,
            article_url=(summary_obj.url if summary_obj and summary_obj.url else (article.url if article else None)),
            sitelinks_count=len(sitelinks),
            match_status=status,
            article_description=summary_obj.description if summary_obj else None,
            article_extract_short=summary_obj.extract if summary_obj else None,
            article_thumbnail_url=summary_obj.thumbnail_url if summary_obj else None,
            article_lat=summary_obj.lat if summary_obj else None,
            article_lon=summary_obj.lon if summary_obj else None,
            article_pageid=summary_obj.pageid if summary_obj else None,
            article_body_text=body,
            geometry_wkt=row.get("geometry_wkt") if has_geom else None,
        ))

    if out_parquet is not None:
        _write_parquet(results, out_parquet)
    if out_jsonl is not None:
        _write_jsonl(results, out_jsonl)

    return results


# --- writers --------------------------------------------------------------

def _write_parquet(results: list[MatchResult], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame([asdict(r) for r in results])
    df.write_parquet(path)


def _write_jsonl(results: list[MatchResult], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in results:
            f.write(json.dumps(asdict(r)) + "\n")


# --- stubs (offline / dev only) -------------------------------------------

def _stub_fetch_sitelinks(qid: str) -> dict[str, dict[str, str]]:
    return {}


def _stub_fetch_summary(lang: str, title: str) -> ArticleSummary | None:
    return None


def _stub_fetch_extract(lang: str, title: str) -> str | None:
    return None