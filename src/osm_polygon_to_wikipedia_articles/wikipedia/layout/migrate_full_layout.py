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

The work is split across small helpers:

- :mod:`._copy_legacy`     — discover + copy legacy flat files
- :mod:`._readme_writers`  — write every README in the layout
- :mod:`._stats`           — shared aggregate-stats helper
- :mod:`.full_layout`      — ``build_all_europe`` + ``build_sample_map``
- :mod:`._manifest`        — manifest + metadata + top-README writers
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from ..visualization.render import render_map_png
from ._copy_legacy import _copy_country_legacy_files, _discover_legacy_slugs
from ._manifest import build_metadata_json, write_manifest_json, write_top_readme
from ._paths import (
    PER_COUNTRY_DIR,
    combined_paths_for,
    country_paths_for,
    preview_paths_for,
    root_paths_for,
    sample_paths_for,
)
from ._readme_writers import (
    write_combined_readme,
    write_per_country_readme,
    write_per_country_top_readme,
    write_preview_readme,
    write_sample_readme,
)
from ._stats import aggregate_stats
from .full_layout import build_all_europe, build_sample_map


def migrate_to_full_layout(
    samples_root: Path,
    *,
    sample_n: int = 4204,
    sample_seed: int = 42,
) -> dict[str, int]:
    """Migrate ``samples_root`` to the canonical layout. Returns a summary."""
    samples_root = Path(samples_root)
    summary = {"countries_migrated": 0, "aux_files_moved": 0}

    # 1. Copy every legacy country's flat files into a subfolder (no deletes).
    legacy_slugs = _discover_legacy_slugs(samples_root)
    for slug in legacy_slugs:
        copied = _copy_country_legacy_files(samples_root, slug)
        if copied:
            summary["countries_migrated"] += 1
            summary["aux_files_moved"] += copied

    # 2. Build the combined union parquet.
    all_europe_pq = build_all_europe(samples_root)

    # 3. Generate the sample JSONL.
    sample_jsonl = build_sample_map(samples_root, target_n=sample_n, seed=sample_seed)

    # 4. Copy or render the preview map.
    preview_pq = preview_paths_for(samples_root).png
    preview_pq.parent.mkdir(parents=True, exist_ok=True)
    preview_html = preview_pq.with_suffix(".html")
    legacy_union_map = samples_root / "all_wikidata_map.png"
    legacy_union_html = samples_root / "all_wikidata_map.html"
    if legacy_union_map.exists() and not preview_pq.exists():
        shutil.copy2(str(legacy_union_map), str(preview_pq))
        summary["aux_files_moved"] += 1
    if legacy_union_html.exists() and not preview_html.exists():
        shutil.copy2(str(legacy_union_html), str(preview_html))
        summary["aux_files_moved"] += 1
    if not preview_pq.exists():
        render_map_png(pl.read_parquet(all_europe_pq), preview_pq)

    # 5. Per-country README + per-folder README.
    df_combined = pl.read_parquet(all_europe_pq)
    for slug in legacy_slugs:
        pq = country_paths_for(samples_root, slug).parquet
        write_per_country_readme(pq)
    n_sample_rows = len(sample_jsonl.read_text().splitlines())
    write_combined_readme(samples_root, df_combined)
    write_sample_readme(samples_root, n_rows=n_sample_rows)
    write_preview_readme(samples_root)

    # 6. Top-level README + manifest + metadata.
    s = aggregate_stats(df_combined)
    write_top_readme(
        samples_root,
        countries=len(s["countries"]),
        total_rows=s["matched"],
        total_words=s["words"],
    )
    write_per_country_top_readme(
        samples_root,
        countries=len(s["countries"]),
        total_rows=s["matched"],
    )
    write_manifest_json(
        samples_root,
        countries=s["countries"],
        combined_rows=s["matched"],
        combined_words=s["words"],
        sample_rows=n_sample_rows,
        svg_count=s["svg"],
    )
    root = root_paths_for(samples_root)
    root.metadata.write_text(build_metadata_json(
        repo_url="https://huggingface.co/datasets/NoeFlandre/osm-polygon-to-wikipedia-articles",
        generated_at=datetime.now(timezone.utc).isoformat(),
        columns=df_combined.columns,
        extra={"combined_words": s["words"], "sample_n": sample_n},
    ))

    return summary


__all__ = ["migrate_to_full_layout"]
