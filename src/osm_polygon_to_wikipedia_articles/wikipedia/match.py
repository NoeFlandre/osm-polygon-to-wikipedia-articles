"""Orchestrator: walk a polygon sample, fetch Wikidata sitelinks, build MatchResult records.

Pure composition over ``wikidata.py`` and ``http_client.py``. Network access is
injected via ``fetch`` so tests can stub it.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Protocol

import polars as pl

from .wikidata import (
    extract_wikidata_qid,
    filter_polygons_with_wikidata,
    resolve_wikidata_to_article,
)


class SitelinksFetcher(Protocol):
    """Anything that turns a QID into a ``sitelinks`` dict (or None on miss)."""

    def __call__(self, qid: str) -> dict[str, dict[str, str]] | None: ...


@dataclass(frozen=True)
class MatchResult:
    """A polygon's Wikidata match outcome."""
    osm_id: int
    osm_type: str
    country: str
    size_bin: str
    centroid_lon: float
    centroid_lat: float
    wikidata_qid: str
    article_title: str | None
    article_lang: str | None
    article_url: str | None
    sitelinks_count: int
    match_status: str  # "matched" | "no_sitelinks" | "no_lang_sitelink"


def match_polygons(
    df: pl.DataFrame,
    lang: str = "en",
    fetch: SitelinksFetcher | None = None,
    out_path: Path | None = None,
) -> list[MatchResult]:
    """For every polygon with a valid ``wikidata=*`` tag, resolve to a Wikipedia article.

    ``fetch`` must be provided in production — it is the HTTP layer (e.g.
    :func:`http_client.fetch_wikidata_sitelinks`). When ``None``, the
    in-memory :func:`_stub_fetch` is used (only useful for offline smoke tests).
    """
    if fetch is None:
        fetch = _stub_fetch

    wd_df = filter_polygons_with_wikidata(df)
    results: list[MatchResult] = []
    for row in wd_df.iter_rows(named=True):
        qid = extract_wikidata_qid(row["tags"])
        if qid is None:
            continue
        sitelinks = fetch(qid) or {}
        article = resolve_wikidata_to_article(qid, lang=lang, sitelinks=sitelinks)

        if not sitelinks:
            status = "no_sitelinks"
        elif article is None:
            status = "no_lang_sitelink"
        else:
            status = "matched"

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
            article_url=article.url if article else None,
            sitelinks_count=len(sitelinks),
            match_status=status,
        ))

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            for r in results:
                f.write(json.dumps(asdict(r)) + "\n")

    return results


def _stub_fetch(qid: str) -> dict[str, dict[str, str]]:
    """Offline stub: useful only for tests/dev. Always returns empty."""
    return {}