#!/usr/bin/env python3
"""Per-country processing audit.

For every country in OSM_DATA_ROOT:
  1. Does the source parquet exist?
  2. Does the _wikidata.parquet exist?
  3. Does data/samples/per_country/<slug>/<slug>.parquet exist?
  4. Match rate (rows / source rows)
  5. Schema: does it have geometry_wkt? thumbnail_is_svg?

Categorises each country into PROCESSED / NEEDS_REPROCESS / NOT_PROCESSED.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import polars as pl

DATA_ROOT = Path(os.environ.get("OSM_DATA_ROOT",
                               "/Volumes/Seagate M3/osm-polygon-to-wikipedia-articles"))
SAMPLES_ROOT = Path("data/samples")

# Required columns for a "clean" processed country
REQUIRED_COLS = {"osm_id", "country", "geometry_wkt",
                 "article_title", "article_body_text", "thumbnail_is_svg"}


def audit(slug: str) -> dict:
    src = DATA_ROOT / f"{slug}.parquet"
    wiki = DATA_ROOT / f"{slug}_wikidata.parquet"
    shipped = SAMPLES_ROOT / "per_country" / slug / f"{slug}.parquet"

    info = {
        "slug": slug,
        "src_exists": src.exists(),
        "wiki_exists": wiki.exists(),
        "shipped_exists": shipped.exists(),
    }

    # Source row count
    if src.exists():
        try:
            info["src_rows"] = pl.read_parquet(src, columns=["osm_id"]).height
        except Exception:
            info["src_rows"] = None
    else:
        info["src_rows"] = None

    # Wiki (matched) row count + schema
    if wiki.exists():
        try:
            df = pl.read_parquet(wiki)
            info["wiki_rows"] = df.height
            cols = set(df.columns)
            info["has_geometry_wkt"] = "geometry_wkt" in cols
            info["has_thumbnail_is_svg"] = "thumbnail_is_svg" in cols
            info["missing_required"] = sorted(REQUIRED_COLS - cols)
            if "article_body_text" in cols:
                info["articles_with_body"] = df["article_body_text"].is_not_null().sum()
            if "geometry_wkt" in cols:
                info["geom_wkt_null_count"] = df["geometry_wkt"].null_count()
            # Match rate
            if info.get("src_rows"):
                info["match_rate"] = round(df.height / info["src_rows"], 4)
        except Exception as e:
            info["wiki_error"] = str(e)
    else:
        info["wiki_rows"] = 0

    return info


def categorise(info: dict) -> str:
    if not info["src_exists"]:
        return "NO_SOURCE"
    if not info["wiki_exists"]:
        return "NOT_PROCESSED"
    if info.get("wiki_rows", 0) == 0:
        return "EMPTY_MATCH"
    if not info.get("shipped_exists"):
        return "PROCESSED_NOT_SHIPPED"
    issues = []
    if not info.get("has_geometry_wkt"):
        issues.append("no_geometry_wkt")
    if not info.get("has_thumbnail_is_svg"):
        issues.append("no_thumbnail_is_svg")
    if info.get("missing_required"):
        issues.append("missing_cols")
    if info.get("geom_wkt_null_count", 0) > 0:
        issues.append(f"geom_null={info['geom_wkt_null_count']}")
    if not issues:
        return "PROCESSED"
    return "NEEDS_REPROCESS"


def main() -> int:
    # 1. All source slugs on disk + the 3 new ones on HF
    on_disk = sorted(p.stem.replace("_wikidata", "")
                     for p in DATA_ROOT.glob("*.parquet")
                     if not p.stem.startswith("all_")
                     and not p.stem.startswith("Seagate"))
    # The 3 new countries (Ireland's actual slug is ireland-and-northern-ireland)
    new_countries = ["ireland-and-northern-ireland", "macedonia", "georgia"]
    all_slugs = sorted(set(on_disk) | set(new_countries))

    print(f"Auditing {len(all_slugs)} countries ({len(on_disk)} on disk + "
          f"{sum(1 for c in new_countries if c not in on_disk)} new on HF)\n")

    rows = []
    for slug in all_slugs:
        info = audit(slug)
        info["category"] = categorise(info)
        rows.append(info)

    # Group by category
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)

    print("=" * 70)
    print("SUMMARY BY CATEGORY")
    print("=" * 70)
    for cat in ["PROCESSED", "NEEDS_REPROCESS", "PROCESSED_NOT_SHIPPED",
                "NOT_PROCESSED", "EMPTY_MATCH", "NO_SOURCE"]:
        if cat not in by_cat:
            continue
        items = by_cat[cat]
        print(f"\n{cat} ({len(items)}):")
        for r in items:
            slug = r["slug"]
            extras = []
            if r.get("wiki_rows") is not None:
                extras.append(f"wiki={r['wiki_rows']}")
            if r.get("src_rows") is not None:
                extras.append(f"src={r['src_rows']}")
            if r.get("match_rate") is not None:
                extras.append(f"rate={r['match_rate']:.1%}")
            if r.get("geom_wkt_null_count", 0) > 0:
                extras.append(f"geom_null={r['geom_wkt_null_count']}")
            print(f"  {slug:32}  {', '.join(extras)}")

    print()
    print("=" * 70)
    print("NEEDS_REPROCESS detail")
    print("=" * 70)
    for r in by_cat.get("NEEDS_REPROCESS", []):
        print(f"  {r['slug']}:")
        for k, v in r.items():
            print(f"    {k}: {v}")
        print()

    out = SAMPLES_ROOT.parent / "audit_results.json"
    out.write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nFull audit written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
