"""Visualize a matches parquet as an HTML map with real polygon outlines.

Reads a parquet with a ``geometry_wkt`` column (e.g.
``data/samples/andorra_wikidata.parquet`` or
``hf://datasets/NoeFlandre/osm-polygon-to-wikipedia-articles/andorra_wikidata.parquet``)
and writes a folium HTML map with one GeoJson polygon per row.

Usage:
    uv run python scripts/visualize_parquet.py \\
        --in data/samples/andorra_wikidata.parquet \\
        --out data/samples/andorra_polygons_map.html \\
        --png data/samples/andorra_polygons_map.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from osm_polygon_to_wikipedia_articles.wikipedia.visualization.geomap import build_polygon_map
from osm_polygon_to_wikipedia_articles.wikipedia.visualization.render import render_map_png


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", type=Path, required=True,
                        help="Input parquet (local path or hf:// URL)")
    parser.add_argument("--out", type=Path, required=True, help="Output HTML map")
    parser.add_argument("--png", type=Path, default=None, help="Optional static PNG screenshot")
    parser.add_argument("--png-width", type=int, default=1000)
    parser.add_argument("--png-height", type=int, default=600)
    args = parser.parse_args()

    df = pl.read_parquet(args.in_path)
    print(f"loaded {df.height} rows from {args.in_path}")
    print(f"columns: {df.columns}")

    n_with_geom = df["geometry_wkt"].is_not_null().sum() if "geometry_wkt" in df.columns else 0
    print(f"rows with geometry_wkt: {n_with_geom}")

    build_polygon_map(df, out_path=args.out)
    print(f"wrote html -> {args.out}")

    if args.png is not None:
        render_map_png(args.out, args.png, width=args.png_width, height=args.png_height)
        print(f"wrote png -> {args.png}")


if __name__ == "__main__":
    main()