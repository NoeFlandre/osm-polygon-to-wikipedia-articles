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
        out_parquet=None,  # we write the filtered parquet ourselves below
        out_jsonl=None,
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

    # Write ONLY the matched polygons to parquet (the public dataset)
    if matched:
        from dataclasses import asdict
        matched_df = pl.DataFrame([asdict(r) for r in matched])
        args.parquet.parent.mkdir(parents=True, exist_ok=True)
        matched_df.write_parquet(args.parquet)
        print(f"\nwrote {len(matched)} matched polygons -> {args.parquet}")
    else:
        print("\n(no matched polygons; nothing written)")

    if args.jsonl is not None:
        from dataclasses import asdict
        import json
        args.jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.jsonl.open("w") as f:
            for r in matched:
                f.write(json.dumps(asdict(r)) + "\n")
        print(f"wrote {len(matched)} matched records -> {args.jsonl}")

    if args.map_path is not None:
        if matched:
            from dataclasses import asdict
            map_df = pl.DataFrame([asdict(r) for r in matched])
            build_map(map_df, out_path=args.map_path)
            print(f"wrote map -> {args.map_path}")
        else:
            print("(no matched polygons; skipping map)")


if __name__ == "__main__":
    main()