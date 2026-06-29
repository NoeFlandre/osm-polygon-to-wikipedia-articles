"""Sample polygons from the osm-polygon-selection HF dataset.

CLI:
    uv run python scripts/sample.py --countries liechtenstein,monaco --n 20
"""
from __future__ import annotations

import argparse
from pathlib import Path

from osm_polygon_to_wikipedia_articles.sample import build_sample

DEFAULT_OUT = Path("data/sample.parquet")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--countries",
        required=True,
        help="Comma-separated country slugs (matches the HF dataset parquet names).",
    )
    parser.add_argument("--n", type=int, default=20, help="Polygons per country.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    countries = [c.strip() for c in args.countries.split(",") if c.strip()]
    df = build_sample(
        countries=countries,
        n_per_country=args.n,
        seed=args.seed,
        out_path=args.out,
    )
    print(f"wrote {df.height} polygons from {len(countries)} countries -> {args.out}")


if __name__ == "__main__":
    main()