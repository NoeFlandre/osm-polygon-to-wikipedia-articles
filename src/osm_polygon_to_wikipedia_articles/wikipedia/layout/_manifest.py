"""Manifest, metadata, and top-level README writers.

Three small text files that sit at the root of the published dataset:

- ``README.md``         — one-screen human summary
- ``manifest``          — JSON structural fingerprint
- ``metadata``          — JSON schema docs

These are the only dataset files a consumer needs to look at first.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from ._paths import (
    COMBINED_DIR,
    COMBINED_PARQUET_NAME,
    PER_COUNTRY_DIR,
    PREVIEW_DIR,
    SAMPLE_DIR,
    SAMPLE_JSONL_NAME,
    PREVIEW_PNG_NAME,
    root_paths_for,
)


def write_manifest_json(
    samples_root: Path,
    *,
    countries: Iterable[str],
    combined_rows: int,
    combined_words: int,
    sample_rows: int,
    svg_count: int,
) -> Path:
    """Write the structural fingerprint of the dataset."""
    paths = root_paths_for(samples_root)
    countries_clean = sorted(c for c in countries if c != "all")
    payload = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "countries": countries_clean,
        "country_count": len(countries_clean),
        "combined_rows": combined_rows,
        "combined_total_words": combined_words,
        "sample_rows": sample_rows,
        "svg_count": svg_count,
        "layout": {
            "per_country": PER_COUNTRY_DIR,
            "combined": COMBINED_DIR,
            "sample": SAMPLE_DIR,
            "preview": PREVIEW_DIR,
        },
        "files": {
            "top_readme": "README.md",
            "manifest": "manifest",
            "metadata": "metadata",
            "combined_parquet": f"{COMBINED_DIR}/{COMBINED_PARQUET_NAME}",
            "sample_jsonl": f"{SAMPLE_DIR}/{SAMPLE_JSONL_NAME}",
            "preview_png": f"{PREVIEW_DIR}/{PREVIEW_PNG_NAME}",
        },
    }
    paths.manifest.write_text(json.dumps(payload, indent=2))
    return paths.manifest


def build_metadata_json(
    *,
    repo_url: str,
    generated_at: str,
    columns: list[str],
    extra: dict | None = None,
) -> str:
    """Render the ``metadata`` file content as a JSON string."""
    payload = {
        "schema_version": "1",
        "repo_url": repo_url,
        "generated_at": generated_at,
        "columns": columns,
        "row_count_approximate": None,
    }
    if extra:
        payload["extra"] = extra
    return json.dumps(payload, indent=2)


def write_top_readme(
    samples_root: Path,
    *,
    countries: int,
    total_rows: int,
    total_words: int,
) -> Path:
    """Write the one-screen human-readable top-level README."""
    p = root_paths_for(samples_root).readme
    text = "\n".join([
        "# OSM-Polygon → Wikipedia Articles",
        "",
        f"- **{countries} countries** processed",
        f"- **{total_rows:,} matched polygons**",
        f"- **{total_words:,} Wikipedia body words**",
        "",
        "## Layout",
        "",
        "```",
        "samples/",
        "├── README.md          ← this file",
        "├── manifest           ← structural fingerprint (JSON)",
        "├── metadata           ← schema docs (JSON)",
        "├── per_country/       ← one folder per country (poland/, italy/, ...)",
        "│   └── <country>/",
        "│       ├── README.md",
        "│       └── <country>.parquet",
        "├── combined/          ← single union parquet",
        "│   ├── README.md",
        "│   └── all_europe.parquet",
        "├── sample/            ← small JSONL for quick inspection",
        "│   ├── README.md",
        "│   └── sample_map.jsonl",
        "└── preview/           ← static map preview",
        "    ├── README.md",
        "    └── map_preview.png",
        "```",
        "",
    ])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


__all__ = ["build_metadata_json", "write_manifest_json", "write_top_readme"]
