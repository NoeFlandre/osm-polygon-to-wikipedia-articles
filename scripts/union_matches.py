"""Union all per-country match JSONLs into one parquet + map + PNG.

Library function lives at :func:`osm_polygon_to_wikipedia_articles.wikipedia.pipeline.union`.

Usage:
    uv run python scripts/union_matches.py \\
        --out data/samples/all_wikidata.parquet \\
        --map data/samples/all_wikidata_map.html \\
        --png data/samples/all_wikidata_map.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.union import (
    SAMPLES_DIR,
    discover_per_country_jsonls,
    union_jsonls,
)
from osm_polygon_to_wikipedia_articles.wikipedia.visualization.map import build_map
from osm_polygon_to_wikipedia_articles.wikipedia.visualization.render import render_map_png


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples-dir", type=Path, default=SAMPLES_DIR)
    parser.add_argument("--out", type=Path, default=SAMPLES_DIR / "all_wikidata.parquet")
    parser.add_argument("--map", dest="map_html", type=Path, default=SAMPLES_DIR / "all_wikidata_map.html")
    parser.add_argument("--png", dest="map_png", type=Path, default=SAMPLES_DIR / "all_wikidata_map.png")
    args = parser.parse_args()

    jsonls = discover_per_country_jsonls(args.samples_dir)
    if not jsonls:
        raise SystemExit(f"no per-country JSONLs found in {args.samples_dir}")

    df = union_jsonls(jsonls, args.out)
    print(f"unioned {len(jsonls)} countries -> {df.height} rows -> {args.out}")

    build_map(df, out_path=args.map_html)
    print(f"wrote map -> {args.map_html}")

    render_map_png(args.map_html, args.map_png, width=1000, height=600)
    print(f"wrote png -> {args.map_png}")


if __name__ == "__main__":
    main()