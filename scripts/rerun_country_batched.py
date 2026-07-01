#!/usr/bin/env python
"""Re-run a country pipeline through batched-sitelinks for speed.

Uses Wikidata's batched ``wbgetentities`` (up to 50 QIDs/request) to fetch
sitelinks, then runs the standard summary + extract fetch for matched rows.

Outputs:
    data/samples/per_country/<slug>/<slug>.parquet (with thumbnail_is_svg)
    data/samples/per_country/<slug>/<slug>_wikidata.jsonl

Usage:
    uv run python scripts/rerun_country_batched.py <country>
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import polars as pl

from osm_polygon_to_wikipedia_articles.wikipedia.batched_sitelinks import (
    fetch_sitelinks_batched,
)
from osm_polygon_to_wikipedia_articles.wikipedia.extracts import fetch_extract
from osm_polygon_to_wikipedia_articles.wikipedia.http_client import (
    fetch_wikipedia_summary,
)
from osm_polygon_to_wikipedia_articles.wikipedia.summary import fetch_summary
from osm_polygon_to_wikipedia_articles.wikipedia.thumbnail import (
    add_thumbnail_columns,
)
from osm_polygon_to_wikipedia_articles.wikipedia.types import MatchResult


def _detect_polygon_centroid(row: dict) -> tuple[float | None, float | None]:
    """Pull a (lon, lat) from whatever centroid columns the source has."""
    for lon_name in ("centroid_lon", "lon", "longitude"):
        if lon_name in row and row[lon_name] is not None:
            try:
                lon = float(row[lon_name])
            except (ValueError, TypeError):
                lon = None
            if lon is not None:
                lat_name = "centroid_lat" if "centroid_lat" in row else "lat" if "lat" in row else "latitude"
                lat = row.get(lat_name)
                try:
                    return lon, float(lat) if lat is not None else None
                except (ValueError, TypeError):
                    return lon, None
    return None, None


def main() -> int:
    country = sys.argv[1] if len(sys.argv) > 1 else None
    if not country:
        print("usage: rerun_country_batched.py <country>"); return 2

    samples = Path("data/samples")
    folder = samples / "per_country" / country
    folder.mkdir(parents=True, exist_ok=True)
    parquet_out = folder / f"{country}.parquet"
    jsonl_out = folder / f"{country}_wikidata.jsonl"

    # Load source polygons from the source dataset
    print(f"[{country}] loading source polygons …", flush=True)
    src_url = f"hf://datasets/NoeFlandre/osm-polygon-selection/per_country/{country}/{country}.parquet"
    df_src = pl.read_parquet(src_url)
    n_src = df_src.height
    print(f"[{country}] source rows: {n_src:,}", flush=True)

    # Filter to wikidata-tagged polygons
    # The source parquet has a ``tags`` column (List[String] of "k=v" pairs).
    # Older sources had a direct ``wikidata`` column.
    wikidata_col = None
    if "wikidata" in df_src.columns:
        wikidata_col = "wikidata"
    elif "tags.wikidata" in df_src.columns:
        wikidata_col = "tags.wikidata"
    if wikidata_col:
        df_wd = df_src.filter(
            pl.col(wikidata_col).is_not_null() & (pl.col(wikidata_col) != "")
        )
    elif "tags" in df_src.columns:
        # Parse tags list to find wikidata= entries
        import json as _j
        def _extract_qid(tags):
            if not isinstance(tags, list):
                return None
            for t in tags:
                if t and isinstance(t, str) and t.startswith("wikidata="):
                    return t.split("=", 1)[1]
            return None
        # Materialise as Python list (cheap; rows are iter_rows'd below)
        rows_with_qid = []
        qids_in_order = []
        for r in df_src.iter_rows(named=True):
            q = _extract_qid(r.get("tags"))
            if q:
                rows_with_qid.append(r)
                qids_in_order.append(q)
        df_wd = pl.DataFrame(rows_with_qid) if rows_with_qid else None
    else:
        print(f"[{country}] no wikidata column", flush=True); return 1

    n_wd = df_wd.height if df_wd is not None else len(rows_with_qid)
    print(f"[{country}] wikidata-tagged: {n_wd:,}", flush=True)

    # Build qid -> row mapping
    rows_by_qid: dict[str, list[dict]] = {}
    if wikidata_col:
        for r in df_wd.iter_rows(named=True):
            qid = r.get(wikidata_col)
            if not qid:
                continue
            if not isinstance(qid, str):
                qid = str(qid)
            rows_by_qid.setdefault(qid, []).append(r)
    else:
        # Already extracted above
        for r, q in zip(rows_with_qid, qids_in_order):
            rows_by_qid.setdefault(q, []).append(r)
    print(f"[{country}] unique QIDs: {len(rows_by_qid):,}", flush=True)

    # Batched sitelinks fetch
    qids = sorted(rows_by_qid.keys())
    print(f"[{country}] batched sitelinks fetch ({len(qids)} qids × ~{len(qids)//50 + 1} batches)…", flush=True)
    t0 = time.time()
    sitelinks_dict = fetch_sitelinks_batched(qids) or {}
    print(f"[{country}] got sitelinks for {len(sitelinks_dict)} qids in {time.time()-t0:.1f}s", flush=True)

    # Walk each polygon: decide matched/no_sitelinks/no_lang_sitelink
    matched: list[MatchResult] = []
    total = 0
    matches = 0
    nsl = 0
    nll = 0
    with jsonl_out.open("w") as jf:
        for qid, rows in rows_by_qid.items():
            sl = sitelinks_dict.get(qid)
            if not sl:
                status = "no_sitelinks"; nsl += 1
                article_lang = None
                article_title = None
                summary_obj = None
                body = None
                article_url = None
                pageid = None
                thumb_url = None
                art_lat = art_lon = None
                description = extract_short = None
                sitelinks_count = 0
            else:
                sitelinks_count = len(sl)
                en = sl.get("enwiki")
                if not en:
                    status = "no_lang_sitelink"; nll += 1
                    article_lang = None
                    article_title = None
                    summary_obj = None
                    body = None
                    article_url = None
                    pageid = None
                    thumb_url = None
                    art_lat = art_lon = None
                    description = extract_short = None
                else:
                    status = "matched"
                    matches += 1
                    article_lang = "en"
                    article_title = en.get("title", "")
                    # fetch summary + extract
                    summary_obj = fetch_summary("en", article_title)
                    body = fetch_extract("en", article_title) or ""
                    article_url = summary_obj.url if summary_obj else f"https://en.wikipedia.org/wiki/{article_title}"
                    pageid = summary_obj.pageid if summary_obj else None
                    thumb_url = summary_obj.thumbnail_url if summary_obj else None
                    art_lat = summary_obj.lat if summary_obj else None
                    art_lon = summary_obj.lon if summary_obj else None
                    description = summary_obj.description if summary_obj else None
                    extract_short = summary_obj.extract if summary_obj else None

            for r in rows:
                total += 1
                centroid_lon, centroid_lat = _detect_polygon_centroid(r)
                geom = r.get("geometry_wkt") or None
                result = MatchResult(
                    osm_id=int(r.get("osm_id") or 0),
                    osm_type=str(r.get("osm_type") or "way"),
                    country=country,
                    size_bin=str(r.get("size_bin") or ""),
                    centroid_lon=centroid_lon,
                    centroid_lat=centroid_lat,
                    wikidata_qid=qid,
                    article_title=article_title or "",
                    article_lang=article_lang or "",
                    article_url=article_url or "",
                    sitelinks_count=int(sitelinks_count),
                    match_status=status,
                    article_description=description,
                    article_extract_short=extract_short,
                    article_thumbnail_url=thumb_url,
                    article_lat=art_lat,
                    article_lon=art_lon,
                    article_pageid=pageid,
                    article_body_text=body or "",
                    geometry_wkt=geom,
                )
                rec = asdict(result)
                jf.write(json.dumps(rec) + "\n")
                if status == "matched":
                    matched.append(rec)

    print(f"[{country}] {total} polygons total: matched={matches}, no_sitelinks={nsl}, no_lang_sitelink={nll}", flush=True)

    if matched:
        df = pl.DataFrame(matched)
        df = add_thumbnail_columns(df)
        df.write_parquet(parquet_out)
        print(f"[{country}] wrote {df.height} matched rows -> {parquet_out}", flush=True)
    else:
        # Write empty with right schema
        df = pl.DataFrame(schema={
            "osm_id": pl.Int64, "osm_type": pl.String, "country": pl.String,
            "size_bin": pl.String, "centroid_lon": pl.Float64, "centroid_lat": pl.Float64,
            "wikidata_qid": pl.String, "article_title": pl.String, "article_lang": pl.String,
            "article_url": pl.String, "sitelinks_count": pl.Int64, "match_status": pl.String,
            "article_description": pl.String, "article_extract_short": pl.String,
            "article_thumbnail_url": pl.String, "article_lat": pl.Float64,
            "article_lon": pl.Float64, "article_pageid": pl.Int64,
            "article_body_text": pl.String, "geometry_wkt": pl.String,
            "thumbnail_is_svg": pl.Boolean,
        })
        df.write_parquet(parquet_out)
        print(f"[{country}] no matches; wrote empty {parquet_out}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
