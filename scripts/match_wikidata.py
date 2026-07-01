"""Resolve Wikidata QIDs for sampled polygons, fetch Wikipedia summaries + bodies,
write parquet + JSONL.

The output parquet is **filtered** to polygons that actually resolved to a
Wikipedia article (``match_status == "matched"``). Optionally renders an HTML
map of the matched polygons.

Usage:
    uv run python scripts/match_wikidata.py \\
        --in data/samples/dev.parquet \\
        --parquet data/samples/dev_wikidata.parquet \\
        --jsonl data/samples/dev_wikidata.jsonl \\
        --map data/samples/dev_wikidata_map.html \\
        --lang en
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import polars as pl

from osm_polygon_to_wikipedia_articles.wikipedia.match import match_polygons
from osm_polygon_to_wikipedia_articles.wikipedia.wikidata import filter_polygons_with_wikidata
from osm_polygon_to_wikipedia_articles.wikipedia.http_client import fetch_wikidata_sitelinks
from osm_polygon_to_wikipedia_articles.wikipedia.summary import fetch_summary
from osm_polygon_to_wikipedia_articles.wikipedia.extracts import fetch_extract
from osm_polygon_to_wikipedia_articles.wikipedia.map import build_map


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", type=Path, default=Path("data/samples/dev.parquet"))
    parser.add_argument("--parquet", type=Path, default=Path("data/samples/dev_wikidata.parquet"))
    parser.add_argument("--jsonl", type=Path, default=None, help="optional, skipped by default")
    parser.add_argument("--map", dest="map_path", type=Path, default=None,
                        help="optional HTML map of matched polygons")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--sleep", type=float, default=0.2, help="seconds between HTTP calls")
    parser.add_argument("--only-wikidata", action="store_true",
                        help="pre-filter the source df to only polygons with wikidata=* tags "
                             "(avoids loading all rows for big countries)")
    parser.add_argument("--max-workers", type=int, default=8,
                        help="number of concurrent polygons to process (default: 8)")
    args = parser.parse_args()

    df = pl.read_parquet(args.in_path)
    if args.only_wikidata:
        before = df.height
        df = filter_polygons_with_wikidata(df)
        print(f"pre-filter (--only-wikidata): {before} -> {df.height} rows")

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
        out_parquet=None,  # we write the filtered parquet ourselves below
        out_jsonl=None,
        max_workers=args.max_workers,
    )

    matched = [r for r in results if r.match_status == "matched"]
    no_lang = [r for r in results if r.match_status == "no_lang_sitelink"]
    no_sl = [r for r in results if r.match_status == "no_sitelinks"]

    print(f"\n{len(results)} polygons with wikidata=*")
    print(f"  matched:           {len(matched)}")
    print(f"  no en sitelink:    {len(no_lang)}")
    print(f"  no sitelinks:      {len(no_sl)}")
    for r in results:
        title = r.article_title or "(no article)"
        body_chars = len(r.article_body_text) if r.article_body_text else 0
        print(f"  {r.wikidata_qid} ({r.country}/{r.osm_type}/{r.osm_id}) -> {r.match_status}: {title}  [body: {body_chars} chars]")

    # Write the parquet (even if 0 rows — validators expect the file to exist)
    from dataclasses import asdict
    matched_df = pl.DataFrame([asdict(r) for r in matched]) if matched else pl.DataFrame(schema={
        "osm_id": pl.Int64, "osm_type": pl.String, "country": pl.String,
        "size_bin": pl.String, "centroid_lon": pl.Float64, "centroid_lat": pl.Float64,
        "wikidata_qid": pl.String, "article_title": pl.String, "article_lang": pl.String,
        "article_url": pl.String, "sitelinks_count": pl.Int64, "match_status": pl.String,
        "article_description": pl.String, "article_extract_short": pl.String,
        "article_thumbnail_url": pl.String, "article_lat": pl.Float64,
        "article_lon": pl.Float64, "article_pageid": pl.Int64,
        "article_body_text": pl.String, "geometry_wkt": pl.String,
    })
    args.parquet.parent.mkdir(parents=True, exist_ok=True)
    matched_df.write_parquet(args.parquet)
    print(f"\nwrote {len(matched)} matched polygons -> {args.parquet}")

    if args.jsonl is not None:
        import json as _json
        args.jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.jsonl.open("w") as f:
            for r in matched:
                f.write(_json.dumps(asdict(r)) + "\n")
        print(f"wrote {len(matched)} matched records -> {args.jsonl}")

    if args.map_path is not None:
        if matched:
            from dataclasses import asdict
            from osm_polygon_to_wikipedia_articles.wikipedia.render import render_map_png
            map_df = pl.DataFrame([asdict(r) for r in matched])
            build_map(map_df, out_path=args.map_path)
            print(f"wrote map -> {args.map_path}")
            png_path = args.map_path.with_suffix(".png")
            render_map_png(args.map_path, png_path, width=1000, height=600)
            print(f"wrote png -> {png_path}")
        else:
            print("(no matched polygons; skipping map)")


if __name__ == "__main__":
    main()