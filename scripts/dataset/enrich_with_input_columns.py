"""Enrich all_wikidata.parquet (and per-country *_wikidata.parquet) with input columns.

Adds ``tags``, ``continent``, ``area_km2``, ``pbf_date`` from the source country
parquets to each per-country wikidata parquet and to the union. No Wikidata
re-fetching; this is a pure column enrichment via left-join on (osm_id, country).
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

ROOT = Path("/Volumes/Seagate M3/osm-polygon-to-wikipedia-articles")
SAMPLES = Path("/Users/noeflandre/osm-polygon-to-wikipedia-articles/data/samples")

INPUT_COLS = ["tags", "continent", "area_km2", "pbf_date"]
JOIN_KEYS = ["osm_id", "country"]


def load_country_input(slug: str) -> pl.DataFrame | None:
    """Read the source country parquet and return only the enrichment columns.

    Deduplicates by (osm_id, country) so the join is one-to-one (some source
    parquets, e.g. france, contain duplicate osm_ids — likely OSM geometry
    splits the same logical polygon across multiple records).
    """
    src = ROOT / f"{slug}.parquet"
    if not src.exists():
        return None
    df = pl.read_parquet(src)
    keep = JOIN_KEYS + [c for c in INPUT_COLS if c in df.columns]
    df = df.select(keep)
    # Keep the first occurrence of each (osm_id, country); the input columns
    # don't usually differ between duplicates, so first-wins is fine.
    return df.unique(subset=JOIN_KEYS, keep="first")


def enrich_one(country: str) -> tuple[int, int]:
    """Enrich one per-country *_wikidata.parquet. Returns (rows_before, rows_after)."""
    out = SAMPLES / f"{country}_wikidata.parquet"
    if not out.exists():
        return (0, 0)
    matched = pl.read_parquet(out)
    if matched.height == 0:
        return (0, 0)
    src = load_country_input(country)
    if src is None:
        return (matched.height, matched.height)
    # Drop any pre-existing enrichment columns to avoid DuplicateError on re-enrichment
    drop = [c for c in INPUT_COLS if c in matched.columns]
    if drop:
        matched = matched.drop(drop)
    before = matched.height
    enriched = matched.join(src, on=JOIN_KEYS, how="left")
    enriched.write_parquet(out)
    return (before, enriched.height)


def enrich_union() -> None:
    """Enrich all_wikidata.parquet by joining all per-country source parquets."""
    union_path = SAMPLES / "all_wikidata.parquet"
    df = pl.read_parquet(union_path)
    countries = df["country"].unique().sort().to_list()
    print(f"enriching union with {len(countries)} countries, {df.height} rows")

    parts: list[pl.DataFrame] = []
    for c in countries:
        src = load_country_input(c)
        if src is not None:
            parts.append(src)
    if not parts:
        print("no input parquets found, aborting")
        return
    inputs = pl.concat(parts, how="vertical_relaxed")
    print(f"  inputs: {inputs.height} rows across {len(parts)} countries")

    # Drop pre-existing enrichment columns to avoid DuplicateError on re-enrichment
    drop = [c for c in INPUT_COLS if c in df.columns]
    if drop:
        df = df.drop(drop)
    enriched = df.join(inputs, on=JOIN_KEYS, how="left")
    # Sanity check: every row should have at least one input column populated
    print(f"  enriched: {enriched.height} rows, columns: {enriched.columns}")
    enriched.write_parquet(union_path)
    print(f"  wrote -> {union_path}")

    # Rebuild the map with the enriched rows (geometry_wkt still drives it)
    from osm_polygon_to_wikipedia_articles.wikipedia.visualization.map import build_map
    from osm_polygon_to_wikipedia_articles.wikipedia.visualization.render import render_map_png
    out_html = SAMPLES / "all_wikidata_map.html"
    out_png = SAMPLES / "all_wikidata_map.png"
    build_map(enriched, out_path=out_html)
    render_map_png(out_html, out_png, width=1000, height=600)
    print(f"  rebuilt map -> {out_html}")
    print(f"  rebuilt png  -> {out_png}")


def main() -> None:
    union_path = SAMPLES / "all_wikidata.parquet"
    df = pl.read_parquet(union_path)
    countries = df["country"].unique().sort().to_list()

    print("=== enriching per-country parquets ===")
    for c in countries:
        before, after = enrich_one(c)
        if before:
            print(f"  {c}: {before} -> {after} rows")

    print("\n=== enriching union ===")
    enrich_union()

    print("\n=== validation ===")
    df = pl.read_parquet(union_path)
    for c in INPUT_COLS:
        if c in df.columns:
            nulls = df[c].null_count()
            print(f"  {c}: {nulls} nulls / {df.height} rows")
        else:
            print(f"  {c}: MISSING COLUMN")


if __name__ == "__main__":
    main()
