"""Resolve Wikidata QIDs for sampled polygons to Wikipedia articles.

Reads ``data/samples/dev.parquet``, finds polygons with ``wikidata=*``,
calls the Wikidata API, writes results to JSONL.

Usage:
    uv run python scripts/match_wikidata.py \\
        --in data/samples/dev.parquet \\
        --out data/samples/dev_wikidata.jsonl \\
        --lang en
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import polars as pl

from osm_polygon_to_wikipedia_articles.wikipedia.wikidata import (
    extract_wikidata_qid,
    filter_polygons_with_wikidata,
    resolve_wikidata_to_article,
)
from osm_polygon_to_wikipedia_articles.wikipedia.http_client import fetch_wikidata_sitelinks


def match_wikidata(
    sample_path: Path,
    out_path: Path,
    lang: str = "en",
    sleep_s: float = 0.2,
) -> list[dict]:
    df = pl.read_parquet(sample_path)
    wd_df = filter_polygons_with_wikidata(df)
    print(f"found {wd_df.height} polygons with wikidata=* in {wd_df['country'].n_unique()} countries")

    results: list[dict] = []
    for row in wd_df.iter_rows(named=True):
        qid = extract_wikidata_qid(row["tags"])
        if qid is None:
            continue
        sitelinks = fetch_wikidata_sitelinks(qid)
        article = resolve_wikidata_to_article(qid, lang=lang, sitelinks=sitelinks) if sitelinks else None

        record = {
            "osm_id": row["osm_id"],
            "osm_type": row["osm_type"],
            "country": row["country"],
            "size_bin": row["size_bin"],
            "centroid_lon": row["centroid_lon"],
            "centroid_lat": row["centroid_lat"],
            "wikidata_qid": qid,
            "article_title": article.title if article else None,
            "article_lang": lang if article else None,
            "article_url": article.url if article else None,
            "sitelinks_count": len(sitelinks) if sitelinks else 0,
            "match_status": "matched" if article else "no_lang_sitelink",
        }
        results.append(record)
        print(f"  {qid} ({row['country']}/{row['osm_type']}/{row['osm_id']}) -> {record['match_status']}: {record['article_title']}")
        time.sleep(sleep_s)  # be polite

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"\nwrote {len(results)} records -> {out_path}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", type=Path, default=Path("data/samples/dev.parquet"))
    parser.add_argument("--out", type=Path, default=Path("data/samples/dev_wikidata.jsonl"))
    parser.add_argument("--lang", default="en")
    parser.add_argument("--sleep", type=float, default=0.2, help="seconds between API calls")
    args = parser.parse_args()
    match_wikidata(args.in_path, args.out, lang=args.lang, sleep_s=args.sleep)


if __name__ == "__main__":
    main()