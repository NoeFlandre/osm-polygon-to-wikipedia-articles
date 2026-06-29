"""Union per-country match JSONLs into one parquet + map.

Library API: :func:`union_jsonls`, :func:`discover_per_country_jsonls`.
CLI: ``uv run python scripts/union_matches.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from .map import build_map
from .render import render_map_png

SAMPLES_DIR = Path("data/samples")


def union_jsonls(jsonl_paths: list[Path], out_parquet: Path) -> pl.DataFrame:
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for p in jsonl_paths:
        for line in p.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    df = pl.DataFrame(rows)
    df.write_parquet(out_parquet)
    return df


def discover_per_country_jsonls(samples_dir: Path = SAMPLES_DIR) -> list[Path]:
    """Find every ``<country>_wikidata.jsonl`` in the samples dir.

    Excludes ``all_wikidata.jsonl`` (which would be the output of this very
    operation) and any non-JSONL files.
    """
    return sorted(
        p for p in samples_dir.glob("*_wikidata.jsonl")
        if not p.name.startswith("all_")
    )