"""README writers for the canonical dataset layout.

Each layout artefact (per-country folder, combined/, sample/, preview/,
per_country/ top) gets a small README. The four writers here are
pure functions — they take the data they need and a target path,
and write the markdown. :func:`aggregate_stats` and :func:`slug_title`
do the heavy lifting.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from ._paths import (
    combined_paths_for,
    country_paths_for,
    preview_paths_for,
    sample_paths_for,
)
from ._readme_tables import headline_table, top_n_table
from ._stats import aggregate_stats, slug_title


def write_per_country_readme(parquet_path: Path) -> Path:
    """Write ``per_country/<slug>/README.md`` from the matching parquet."""
    slug = parquet_path.parent.name
    paths = country_paths_for(parquet_path.parents[2], slug)
    if not parquet_path.exists():
        paths.readme.write_text(
            f"# {slug_title(slug)}\n\n*No matched polygons for this country yet.*\n"
        )
        return paths.readme

    df = pl.read_parquet(parquet_path)
    s = aggregate_stats(df)
    title = slug_title(slug)
    lines = [
        f"# {title}",
        "",
        "Per-country snapshot of OSM polygons that resolved to an English",
        "Wikipedia article via the `enwiki` Wikidata sitelink.",
        "",
        "## Headline numbers",
        "",
        headline_table(s),
        "",
        "## Files in this folder",
        "",
        f"- `{slug}.parquet` — slim per-country table",
        f"- `{slug}_wikidata.jsonl` — full per-polygon trace",
        f"- `{slug}_wikidata_map.html` — interactive Folium map",
        f"- `{slug}_wikidata_map.png` — static snapshot",
        "",
    ]
    if s["matched"] > 0 and "article_title" in df.columns:
        top = (
            df.group_by("article_title")
            .len()
            .sort("len", descending=True)
            .head(10)
        )
        rows = [(r["article_title"], int(r["len"]))
                for r in top.iter_rows(named=True)]
        lines += [
            top_n_table(
                title="Top articles by polygon count",
                rows=rows,
                headers=("Article", "Polygons"),
            ),
            "",
        ]

    paths.readme.write_text("\n".join(lines))
    return paths.readme


def write_combined_readme(samples_root: Path, df: pl.DataFrame) -> Path:
    """Write ``combined/README.md`` from the combined DataFrame."""
    s = aggregate_stats(df)
    paths = combined_paths_for(samples_root)
    lines = [
        "# combined/all_europe.parquet",
        "",
        f"Single concat of every per-country parquet: **{s['matched']:,}** matched",
        f"polygons across **{len(s['countries'])}** countries. This is the same",
        "data you'd reconstruct by reading every `per_country/<slug>/...",
        "_wikidata.parquet` and concatenating, but pre-merged so consumers",
        "don't have to.",
        "",
        "## Headline numbers",
        "",
        headline_table(s),
        "",
    ]
    if "country" in df.columns and df.height > 0:
        top = (
            df.group_by("country")
            .len()
            .sort("len", descending=True)
            .head(15)
        )
        rows = [(r["country"], int(r["len"]))
                for r in top.iter_rows(named=True)]
        lines += [
            top_n_table(
                title="Top contributors by matched polygons",
                rows=rows,
                headers=("Country", "Polygons"),
            ),
            "",
        ]

    paths.readme.parent.mkdir(parents=True, exist_ok=True)
    paths.readme.write_text("\n".join(lines))
    return paths.readme


def write_sample_readme(samples_root: Path, n_rows: int) -> Path:
    """Write ``sample/README.md`` from the sample size."""
    paths = sample_paths_for(samples_root)
    paths.readme.parent.mkdir(parents=True, exist_ok=True)
    paths.readme.write_text(
        "\n".join([
            "# sample/sample_map.jsonl",
            "",
            f"Small uniform-random sample of **{n_rows:,}** polygons from the",
            "combined aggregate for quick inspection. Same schema as the per-country",
            "tables, one JSON record per line so the file is stream-friendly.",
            "",
            f"- Records: {n_rows:,}",
            f"- Generator: deterministic (seed=42 by default)",
            "",
        ])
    )
    return paths.readme


def write_preview_readme(samples_root: Path) -> Path:
    """Write ``preview/README.md`` from the preview png size."""
    paths = preview_paths_for(samples_root)
    png_size = paths.png.stat().st_size if paths.png.exists() else 0
    paths.readme.parent.mkdir(parents=True, exist_ok=True)
    paths.readme.write_text(
        "\n".join([
            "# preview/map_preview.png",
            "",
            "Static world overview map of every matched polygon across the",
            "combined dataset. Useful to eyeball the coverage at a glance —",
            "open `combined/README.md` for the interactive version per country.",
            "",
            f"- File size: {png_size:,} bytes",
            "",
        ])
    )
    return paths.readme


def write_per_country_top_readme(samples_root: Path, *, countries: int, total_rows: int) -> Path:
    """Write ``per_country/README.md`` (the one inside the per_country folder itself)."""
    p = samples_root / "per_country" / "README.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join([
            "# per_country/",
            "",
            "One folder per country processed by the pipeline. Each",
            "folder ships the canonical parquet plus the matching",
            "interactive/static map files for that country.",
            "",
            f"- {countries} countries",
            f"- {total_rows:,} matched polygons across all of them",
            "",
        ])
    )
    return p


__all__ = [
    "write_combined_readme",
    "write_per_country_readme",
    "write_per_country_top_readme",
    "write_preview_readme",
    "write_sample_readme",
]
