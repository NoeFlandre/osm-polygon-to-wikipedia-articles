"""Migrate a flat ``samples/`` directory into the canonical four-subfolder layout.

Reads the legacy layout (one flat ``<slug>_wikidata.{parquet,jsonl,html,png}``
file set per country plus the union aggregate at the top level) and produces:

    samples/
    ├── README.md
    ├── manifest                              (JSON structural fingerprint)
    ├── metadata                              (JSON schema docs)
    ├── per_country/                          46 country subfolders
    │   ├── README.md
    │   ├── <slug>/README.md
    │   └── <slug>/<slug>.parquet (+map.html, .png, .jsonl)
    ├── combined/
    │   ├── README.md
    │   └── all_europe.parquet
    ├── sample/
    │   ├── README.md
    │   └── sample_map.jsonl
    └── preview/
        ├── README.md
        └── map_preview.png

Idempotent: re-running on the canonical layout is a safe no-op.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl

from .full_layout import (
    COMBINED_PARQUET_NAME,
    PREVIEW_PNG_NAME,
    SAMPLE_JSONL_NAME,
    build_all_europe,
    build_metadata_json,
    build_sample_map,
    combined_paths_for,
    country_paths_for,
    preview_paths_for,
    root_paths_for,
    sample_paths_for,
    write_manifest_json,
    write_top_readme,
)
from ..visualization.render import render_map_png


# --- Path constants for the legacy flat layout --------------------------

_LEGACY_FILE_EXTENSIONS = ("parquet", "jsonl", "html", "png")


def _flat_paths(samples_root: Path, slug: str) -> dict[str, Path]:
    """Return the four legacy flat paths for a country (one per file type)."""
    return {
        ext: samples_root / f"{slug}_wikidata.{ext}"
        for ext in _LEGACY_FILE_EXTENSIONS
    }


def _is_legacy_country(samples_root: Path, slug: str) -> bool:
    return (samples_root / f"{slug}_wikidata.parquet").exists() or (
        samples_root / f"{slug}_wikidata.jsonl"
    ).exists()


def _discover_legacy_slugs(samples_root: Path) -> list[str]:
    """Pick up country slugs from any of the legacy flat patterns.

    Excludes:
    - ``all`` (the union aggregate, not a country)
    - any folder name that isn't actually a country code
    """
    slugs: set[str] = set()
    patterns = [
        "*_wikidata.parquet",
        "*_wikidata.jsonl",
        "*_wikidata_map.html",
        "*_wikidata_map.png",
        "*_polygons_map.html",
        "*_polygons_map.png",
    ]
    for pattern in patterns:
        for p in samples_root.glob(pattern):
            stem = p.stem  # e.g. "poland_wikidata_map"
            slug = None
            # Longest suffix first so "_wikidata_map" matches before "_wikidata".
            for suffix in ("_wikidata_map", "_polygons_map", "_wikidata"):
                if stem.endswith(suffix):
                    slug = stem[: -len(suffix)]
                    break
            if slug and slug != "all":
                slugs.add(slug)
    return sorted(slugs)


def _move_legacy_country(samples_root: Path, slug: str) -> dict[str, int]:
    """Copy a country's legacy flat files into the new subfolder (no delete).

    We *copy* (not move) so the original flat files stay at samples root for
    backward compatibility — the user explicitly asked to keep both layouts
    until they approve any deletes. After copying we have:

    - ``<slug>.parquet`` — copy of ``<slug>_wikidata.parquet``
    - ``<slug>_wikidata.jsonl`` — copy of ``<slug>_wikidata.jsonl``
    - ``<slug>_wikidata_map.{html,png}`` — copy of legacy aux maps
    """
    moves = {"parquet": 0, "jsonl": 0, "html": 0, "png": 0}
    flat = _flat_paths(samples_root, slug)
    targets = country_paths_for(samples_root, slug)
    targets.folder.mkdir(parents=True, exist_ok=True)
    for ext, src in flat.items():
        if not src.exists():
            continue
        target_name = (
            f"{slug}.parquet" if ext == "parquet"
            else f"{slug}_wikidata.{ext}"
        )
        dst = targets.folder / target_name
        if src != dst and src.exists() and not dst.exists():
            shutil.copy2(str(src), str(dst))
            moves[ext] += 1
    return moves


# --- Pattern-1: variants ------------------------------------------------


def _copy_legacy_aux_maps(samples_root: Path, slug: str) -> dict[str, int]:
    """Copy any auxiliary map files (with `_wikidata_map` or `_polygons_map`
    suffix) for a slug into its subfolder. Safe (skip if destination exists,
    never delete at source).

    Destination filename preserves the original variant:
    - ``<slug>_wikidata_map.{html,png}`` ← from `<slug>_wikidata_map.*`
    - ``<slug>_polygons_map.{html,png}`` ← from `<slug>_polygons_map.*`
    """
    moves = {"html": 0, "png": 0}
    targets = country_paths_for(samples_root, slug)
    targets.folder.mkdir(parents=True, exist_ok=True)
    # (source-suffix, destination-suffix) — destination keeps the same suffix
    pairs = (
        ("_wikidata_map", "_wikidata_map"),
        ("_polygons_map", "_polygons_map"),
    )
    for src_suffix, dst_suffix in pairs:
        for ext in ("html", "png"):
            src = samples_root / f"{slug}{src_suffix}.{ext}"
            if not src.exists():
                continue
            dst = targets.folder / f"{slug}{dst_suffix}.{ext}"
            if not dst.exists():
                shutil.copy2(str(src), str(dst))
                moves[ext] += 1
    return moves


# --- per-country README + per-folder README writers ---------------------


def _write_per_country_readme(samples_root: Path, slug: str, parquet_path: Path) -> Path:
    paths = country_paths_for(samples_root, slug)
    df = pl.read_parquet(parquet_path) if parquet_path.exists() else None
    if df is None or df.height == 0:
        body = [
            f"# {slug.replace('-', ' ').title()}",
            "",
            "*No matched polygons for this country yet.*",
            "",
        ]
        paths.readme.write_text("\n".join(body))
        return paths.readme

    matched = df.height
    svg = int(df["thumbnail_is_svg"].sum()) if "thumbnail_is_svg" in df.columns else 0
    body_text_total = sum(
        len(t.split()) for t in df["article_body_text"].to_list() if t
    )

    title = slug.replace("-", " ").title()
    lines = [
        f"# {title}",
        "",
        "Per-country snapshot of OSM polygons that resolved to an English",
        f"Wikipedia article via the `enwiki` Wikidata sitelink.",
        "",
        "## Headline numbers",
        "",
        "| Metric | Value |",
        "| ------ | ----- |",
        f"| Matched polygons | {matched:,} |",
        f"| SVG thumbnails | {svg:,} |",
        f"| Wikipedia body words | {body_text_total:,} |",
        "",
        "## Files in this folder",
        "",
        f"- `{slug}.parquet` — slim per-country table",
        f"- `{slug}_wikidata.jsonl` — full per-polygon trace",
        f"- `{slug}_wikidata_map.html` — interactive Folium map",
        f"- `{slug}_wikidata_map.png` — static snapshot",
        "",
    ]

    if "article_title" in df.columns and matched > 0:
        top = (
            df.group_by("article_title")
            .len()
            .sort("len", descending=True)
            .head(10)
        )
        lines += [
            "## Top articles by polygon count",
            "",
            "| Article | Polygons |",
            "| ------- | -------- |",
        ]
        for r in top.iter_rows(named=True):
            lines.append(f"| {r['article_title']} | {r['len']} |")
        lines.append("")

    paths.readme.write_text("\n".join(lines))
    return paths.readme


def _write_subfolder_readme(folder: Path, title: str, body: list[str]) -> Path:
    text = "\n".join([f"# {title}", ""] + body)
    readme = folder / "README.md"
    readme.write_text(text)
    return readme


def _write_combined_readme(samples_root: Path, df: pl.DataFrame) -> Path:
    paths = combined_paths_for(samples_root)
    matched = df.height
    svg = int(df["thumbnail_is_svg"].sum()) if "thumbnail_is_svg" in df.columns else 0
    body_text_total = sum(
        len(t.split()) for t in df["article_body_text"].to_list() if t
    )
    countries = sorted(df["country"].unique().to_list()) if "country" in df.columns else []
    top = (
        df.group_by("country")
        .len()
        .sort("len", descending=True)
        .head(15)
        if "country" in df.columns
        else None
    )
    lines = [
        f"# combined/all_europe.parquet",
        "",
        f"Single concat of every per-country parquet: **{matched:,}** matched",
        f"polygons across **{len(countries)}** countries. This is the same",
        "data you'd reconstruct by reading every `per_country/<slug>/...",
        "_wikidata.parquet` and concatenating, but pre-merged so consumers",
        "don't have to.",
        "",
        "## Headline numbers",
        "",
        "| Metric | Value |",
        "| ------ | ----- |",
        f"| Matched polygons | {matched:,} |",
        f"| SVG thumbnails | {svg:,} |",
        f"| Wikipedia body words | {body_text_total:,} |",
        "",
    ]
    if top is not None and top.height > 0:
        lines += [
            "## Top contributors by matched polygons",
            "",
            "| Country | Polygons |",
            "| ------- | -------- |",
        ]
        for r in top.iter_rows(named=True):
            lines.append(f"| {r['country']} | {r['len']:,} |")
        lines.append("")
    paths.readme.parent.mkdir(parents=True, exist_ok=True)
    paths.readme.write_text("\n".join(lines))
    return paths.readme


def _write_sample_readme(samples_root: Path, n_rows: int) -> Path:
    paths = sample_paths_for(samples_root)
    lines = [
        "# sample/sample_map.jsonl",
        "",
        f"Small uniform-random sample of **{n_rows:,}** polygons from the",
        "combined aggregate for quick inspection. Same schema as the per-country",
        "tables, one JSON record per line so the file is stream-friendly.",
        "",
        f"- Records: {n_rows:,}",
        f"- Generator: deterministic (seed=42 by default)",
        "",
    ]
    paths.readme.parent.mkdir(parents=True, exist_ok=True)
    paths.readme.write_text("\n".join(lines))
    return paths.readme


def _write_preview_readme(samples_root: Path) -> Path:
    paths = preview_paths_for(samples_root)
    png_size = paths.png.stat().st_size if paths.png.exists() else 0
    lines = [
        "# preview/map_preview.png",
        "",
        "Static world overview map of every matched polygon across the",
        "combined dataset. Useful to eyeball the coverage at a glance —",
        "open `combined/README.md` for the interactive version per country.",
        "",
        f"- File size: {png_size:,} bytes",
        "",
    ]
    paths.readme.parent.mkdir(parents=True, exist_ok=True)
    paths.readme.write_text("\n".join(lines))
    return paths.readme


# --- Main migration entry point -----------------------------------------


def migrate_to_full_layout(
    samples_root: Path,
    *,
    sample_n: int = 4204,
    sample_seed: int = 42,
) -> dict[str, int]:
    """Migrate ``samples_root`` to the canonical layout. Returns a summary."""
    samples_root = Path(samples_root)
    summary: dict[str, int] = {
        "countries_migrated": 0,
        "aux_files_moved": 0,
    }

    # 1. Copy every legacy country's flat files into a subfolder (no deletes).
    legacy_slugs = _discover_legacy_slugs(samples_root)
    new_slugs: list[str] = []
    for slug in legacy_slugs:
        primary = _move_legacy_country(samples_root, slug)
        aux = _copy_legacy_aux_maps(samples_root, slug)
        total = sum(primary.values()) + sum(aux.values())
        summary["countries_migrated"] += 1 if total else 0
        summary["aux_files_moved"] += total
        new_slugs.append(slug)

    # 2. Build all_europe.parquet from the per_country folders.
    all_europe_pq = build_all_europe(samples_root)

    # 3. Generate sample_map.jsonl
    sample_jsonl = build_sample_map(
        samples_root,
        target_n=sample_n,
        seed=sample_seed,
    )

    # 4. Copy the legacy union map png → preview/map_preview.png (no delete at source)
    legacy_union_map = samples_root / "all_wikidata_map.png"
    legacy_union_html = samples_root / "all_wikidata_map.html"
    preview_pq = preview_paths_for(samples_root).png
    preview_pq.parent.mkdir(parents=True, exist_ok=True)
    # Also copy the html version alongside if present.
    preview_html = preview_pq.with_suffix(".html")
    if legacy_union_map.exists() and not preview_pq.exists():
        shutil.copy2(str(legacy_union_map), str(preview_pq))
        summary["aux_files_moved"] += 1
    if legacy_union_html.exists() and not preview_html.exists():
        shutil.copy2(str(legacy_union_html), str(preview_html))
        summary["aux_files_moved"] += 1
    # If neither legacy exists and preview_pq is missing, render fresh.
    if not preview_pq.exists():
        df_combined = pl.read_parquet(all_europe_pq)
        render_map_png(df_combined, preview_pq)

    # 5. Render per-country and folder READMEs.
    df_combined = pl.read_parquet(all_europe_pq)
    for slug in sorted(new_slugs):
        pq = country_paths_for(samples_root, slug).parquet
        _write_per_country_readme(samples_root, slug, pq)

    # 6. Write per-folder READMEs.
    _write_combined_readme(samples_root, df_combined)
    _write_sample_readme(samples_root, n_rows=len(sample_jsonl.read_text().splitlines()))
    _write_preview_readme(samples_root)

    # 7. Build the top-level README + manifest + metadata.
    countries_count = (
        df_combined["country"].n_unique() if "country" in df_combined.columns else 0
    )
    total_rows = df_combined.height
    total_words = sum(
        len(t.split()) for t in df_combined["article_body_text"].to_list() if t
    )
    svg_count = (
        int(df_combined["thumbnail_is_svg"].sum())
        if "thumbnail_is_svg" in df_combined.columns
        else 0
    )

    write_top_readme(
        samples_root,
        countries=countries_count,
        total_rows=total_rows,
        total_words=total_words,
    )

    # Per-country top-level README inside per_country/
    pc_readme = samples_root / "per_country" / "README.md"
    pc_readme.parent.mkdir(parents=True, exist_ok=True)
    pc_readme.write_text(
        "\n".join([
            "# per_country/",
            "",
            f"One folder per country processed by the pipeline. Each",
            f"folder ships the canonical parquet plus the matching",
            f"interactive/static map files for that country.",
            "",
            f"- {countries_count} countries",
            f"- {total_rows:,} matched polygons across all of them",
            "",
        ])
    )

    # Manifest + metadata
    write_manifest_json(
        samples_root,
        countries=df_combined["country"].unique().to_list() if "country" in df_combined.columns else [],
        combined_rows=total_rows,
        combined_words=total_words,
        sample_rows=len(sample_jsonl.read_text().splitlines()),
        svg_count=svg_count,
    )

    root = root_paths_for(samples_root)
    if df_combined is not None:
        cols = df_combined.columns
    else:
        cols = []
    root.metadata.write_text(build_metadata_json(
        repo_url="https://huggingface.co/datasets/NoeFlandre/osm-polygon-to-wikipedia-articles",
        generated_at="2026-07-01T00:00:00Z",
        columns=cols,
        extra={"combined_words": total_words, "sample_n": sample_n},
    ))

    return summary
