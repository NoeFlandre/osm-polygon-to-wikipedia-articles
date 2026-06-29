"""Resolve Wikidata QIDs for sampled polygons to Wikipedia articles.

Thin CLI over :func:`osm_polygon_to_wikipedia_articles.wikipedia.match.match_polygons`.

Usage:
    uv run python scripts/match_wikidata.py \\
        --in data/samples/dev.parquet \\
        --out data/samples/dev_wikidata.jsonl \\
        --lang en
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from osm_polygon_to_wikipedia_articles.wikipedia.match import match_polygons
from osm_polygon_to_wikipedia_articles.wikipedia.http_client import fetch_wikidata_sitelinks

import polars as pl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", type=Path, default=Path("data/samples/dev.parquet"))
    parser.add_argument("--out", type=Path, default=Path("data/samples/dev_wikidata.jsonl"))
    parser.add_argument("--lang", default="en")
    parser.add_argument("--sleep", type=float, default=0.2, help="seconds between API calls")
    args = parser.parse_args()

    df = pl.read_parquet(args.in_path)

    def fetch(qid: str):
        result = fetch_wikidata_sitelinks(qid)
        time.sleep(args.sleep)
        return result

    results = match_polygons(df, lang=args.lang, fetch=fetch, out_path=args.out)

    print(f"\n{len(results)} polygons matched")
    for r in results:
        title = r.article_title or "(no article)"
        print(f"  {r.wikidata_qid} ({r.country}/{r.osm_type}/{r.osm_id}) -> {r.match_status}: {title}")
    print(f"\nwrote {len(results)} records -> {args.out}")


if __name__ == "__main__":
    main()