"""Orchestrator: walk a polygon sample, fetch Wikidata + Wikipedia article data.

Pure composition over ``wikidata.py``, ``summary.py``, ``extracts.py``. Network
access is injected via ``fetch_sitelinks``, ``fetch_summary``, ``fetch_extract``
so tests can stub it.

Two execution modes:

1. **Sequential** (default, ``max_workers=1``): one polygon at a time.
2. **Concurrent** (``max_workers>1``): one thread per polygon, all three
   fetches per polygon run inline within that thread. Default ``max_workers=8``.

**Resumability**: ``resume_jsonl`` (and/or ``out_jsonl``) is consulted at
startup. Polygons whose ``(osm_id, country)`` is already in the file are
skipped — their previous ``MatchResult`` is appended to the output as-is. JSONL
is written incrementally after each polygon, so a Ctrl-C / crash leaves the
file usable as a resume checkpoint.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Iterable, Protocol

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


def _process_one(
    row: dict,
    lang: str,
    fetch_sitelinks: SitelinksFetcher,
    fetch_summary: SummaryFetcher,
    fetch_extract: ExtractFetcher,
) -> MatchResult | None:
    """Run the full sitelink -> summary -> extract pipeline for one polygon."""
    has_geom = "geometry_wkt" in row
    qid = extract_wikidata_qid(row.get("tags"))
    if qid is None:
        return None

    sitelinks = fetch_sitelinks(qid) or {}
    article = resolve_wikidata_to_article(qid, lang=lang, sitelinks=sitelinks)

    if not sitelinks:
        status = "no_sitelinks"
    elif article is None:
        status = "no_lang_sitelink"
    else:
        status = "matched"

    summary_obj: ArticleSummary | None = None
    body: str | None = None
    if article is not None:
        summary_obj = fetch_summary(lang, article.title)
        body = fetch_extract(lang, article.title)

    return MatchResult(
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
    )


def _load_resume_keys(path: Path | None) -> set[tuple[int, str]]:
    """Return the set of (osm_id, country) pairs already present in ``path``."""
    if path is None or not path.exists():
        return set()
    keys: set[tuple[int, str]] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        keys.add((rec["osm_id"], rec["country"]))
    return keys


def _load_resume_results(path: Path | None) -> list[dict]:
    """Return all prior MatchResult dicts from ``path``, in insertion order."""
    if path is None or not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def match_polygons(
    df: pl.DataFrame,
    lang: str = "en",
    *,
    fetch_sitelinks: SitelinksFetcher | None = None,
    fetch_summary: SummaryFetcher | None = None,
    fetch_extract: ExtractFetcher | None = None,
    out_parquet: Path | None = None,
    out_jsonl: Path | None = None,
    max_workers: int = 8,
    resume_jsonl: Path | None = None,
) -> list[MatchResult]:
    """For every polygon with a valid ``wikidata=*`` tag:

    1. resolve to the Wikipedia article title via Wikidata sitelinks
    2. fetch the REST summary (extract, description, thumbnail, coords, pageid, url)
    3. fetch the plain-text body of the article

    Concurrent when ``max_workers > 1``; resumable against ``resume_jsonl``.
    """
    fetch_sitelinks = fetch_sitelinks or _stub_fetch_sitelinks
    fetch_summary = fetch_summary or _stub_fetch_summary
    fetch_extract = fetch_extract or _stub_fetch_extract

    wd_df = filter_polygons_with_wikidata(df)

    # Load prior results from resume_jsonl (also use out_jsonl as a fallback)
    resume_source = resume_jsonl or out_jsonl
    prior_dicts = _load_resume_results(resume_source)
    prior_results = [MatchResult(**d) for d in prior_dicts]
    prior_keys = {(r.osm_id, r.country) for r in prior_results}

    rows_to_process: list[dict] = [
        r for r in wd_df.iter_rows(named=True)
        if (r["osm_id"], r["country"]) not in prior_keys
    ]

    # Open the JSONL for incremental append
    jsonl_fp = None
    if out_jsonl is not None:
        out_jsonl = Path(out_jsonl)
        out_jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl_fp = out_jsonl.open("a")

    try:
        if max_workers <= 1:
            for row in rows_to_process:
                result = _process_one(row, lang, fetch_sitelinks, fetch_summary, fetch_extract)
                if result is None:
                    continue
                prior_results.append(result)
                if jsonl_fp is not None:
                    jsonl_fp.write(json.dumps(asdict(result)) + "\n")
                    jsonl_fp.flush()
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                # Tag each future with its input position so we can sort by input
                # order at the end (as_completed yields in arbitrary order).
                futures = {
                    ex.submit(
                        _process_one, row, lang, fetch_sitelinks, fetch_summary, fetch_extract
                    ): (idx, row)
                    for idx, row in enumerate(rows_to_process)
                }
                indexed: list[tuple[int, MatchResult]] = []
                for fut in as_completed(futures):
                    idx, _row = futures[fut]
                    result = fut.result()
                    if result is None:
                        continue
                    indexed.append((idx, result))
                    if jsonl_fp is not None:
                        jsonl_fp.write(json.dumps(asdict(result)) + "\n")
                        jsonl_fp.flush()
                # Append in input order so callers get a stable sequence.
                for _, result in sorted(indexed, key=lambda x: x[0]):
                    prior_results.append(result)
    finally:
        if jsonl_fp is not None:
            jsonl_fp.close()

    if out_parquet is not None:
        _write_parquet(prior_results, out_parquet)

    return prior_results


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


__all__ = ["match_polygons"]