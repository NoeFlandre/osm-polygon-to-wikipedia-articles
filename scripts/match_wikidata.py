"""Resolve Wikidata QIDs for sampled polygons, fetch Wikipedia summaries + bodies,
write parquet + JSONL.

Usage:
    uv run python scripts/match_wikidata.py \\
        --in data/samples/dev.parquet \\
        --parquet data/samples/dev_wikidata.parquet \\
        --jsonl data/samples/dev_wikidata.jsonl \\
        --lang en
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import polars as pl

from osm_polygon_to_wikipedia_articles.wikipedia.match import match_polygons
from osm_polygon_to_wikipedia_articles.wikipedia.http_client import fetch_wikidata_sitelinks
from osm_polygon_to_wikipedia_articles.wikipedia.summary import fetch_summary
from osm_polygon_to_wikipedia_articles.wikipedia.extracts import fetch_extract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", type=Path, default=Path("data/samples/dev.parquet"))
    parser.add_argument("--parquet", type=Path, default=Path("data/samples/dev_wikidata.parquet"))
    parser.add_argument("--jsonl", type=Path, default=None, help="optional, skipped by default")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--sleep", type=float, default=0.2, help="seconds between HTTP calls")
    args = parser.parse_args()

    df = pl.read_parquet(args.in_path)

    def _sitelinks(qid: str):
        result = fetch_wikidata_sitelinks(qid)
        time.sleep(args.sleep)
        return result

    def _summary(lang: str, title: str):
        s = fetch_summary(lang=lang, title=title)
        time.sleep(args.sleep)
        return s

    def _extract(lang: str, title: str):
        e = fetch_extract(lang=lang, title=title)
        time.sleep(args.sleep)
        return e

    results = match_polygons(
        df,
        lang=args.lang,
        fetch_sitelinks=_sitelinks,
        fetch_summary=_summary,
        fetch_extract=_extract,
        out_parquet=args.parquet,
        out_jsonl=args.jsonl,
    )

    matched = sum(1 for r in results if r.match_status == "matched")
    no_lang = sum(1 for r in results if r.match_status == "no_lang_sitelink")
    no_sl = sum(1 for r in results if r.match_status == "no_sitelinks")
    print(f"\n{len(results)} polygons with wikidata=*")
    print(f"  matched:           {matched}")
    print(f"  no en sitelink:    {no_lang}")
    print(f"  no sitelinks:      {no_sl}")
    for r in results:
        title = r.article_title or "(no article)"
        body_chars = len(r.article_body_text) if r.article_body_text else 0
        print(f"  {r.wikidata_qid} ({r.country}/{r.osm_type}/{r.osm_id}) -> {r.match_status}: {title}  [body: {body_chars} chars]")
    print(f"\nwrote parquet -> {args.parquet}")
    if args.jsonl:
        print(f"wrote jsonl   -> {args.jsonl}")


if __name__ == "__main__":
    main()