#!/usr/bin/env python3
"""Post-process a country: add_thumbnail_columns, write README, push to HF.

Usage:
    uv run python scripts/dataset/finish_and_push_country.py <slug>

Expects:
    data/samples/per_country/<slug>/<slug>.parquet  (from rerun_country_batched.py)
    data/samples/per_country/<slug>/<slug>_wikidata.jsonl
"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

from osm_polygon_to_wikipedia_articles.wikipedia.layout._readme_writers import (
    write_per_country_readme,
)


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else None
    if not slug:
        print("usage: finish_and_push_country.py <slug>"); return 2

    folder = Path("data/samples/per_country") / slug
    parquet = folder / f"{slug}.parquet"

    if not parquet.exists():
        print(f"missing {parquet}"); return 1

    # 1. Re-run add_thumbnail_columns in case any new SVGs slipped in
    from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.thumbnail import (
        add_thumbnail_columns,
    )
    df = pl.read_parquet(parquet)
    if "thumbnail_is_svg" not in df.columns:
        df = add_thumbnail_columns(df)
        df.write_parquet(parquet)
        print(f"  added thumbnail_is_svg: {df.height} rows")
    else:
        print(f"  thumbnail_is_svg already present ({df.height} rows)")

    # 2. Write per-country README
    write_per_country_readme(parquet)
    print(f"  wrote README.md")

    # 3. Push to HF
    import subprocess
    res = subprocess.run(
        ["hf", "upload", "NoeFlandre/osm-polygon-to-wikipedia-articles",
         str(folder.absolute()),
         "--repo-type=dataset",
         "--include", f"{slug}/*"],
        check=True,
    )
    print(f"  pushed to HF")
    return 0


if __name__ == "__main__":
    sys.exit(main())
