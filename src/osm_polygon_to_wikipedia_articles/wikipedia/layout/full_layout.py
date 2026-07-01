"""Builders for the canonical 4-subfolder layout.

Three pure functions that read the per-country parquets and produce the
combined / sample / preview artefacts:

- :func:`discover_country_parquets` — every per-country parquet
- :func:`build_all_europe`          — single union parquet
- :func:`build_sample_map`          — small uniform-random JSONL sample

Path dataclasses and ``*_paths_for`` factories live in
:mod:`.layout._paths`. Manifest/metadata/top-README writers live in
:mod:`.layout._manifest`.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import polars as pl

from ._paths import (
    COMBINED_PARQUET_NAME,
    PER_COUNTRY_DIR,
    combined_paths_for,
    sample_paths_for,
)


def discover_country_parquets(samples_root: Path) -> list[Path]:
    """Return sorted list of every per-country parquet file (legacy or new).

    Excludes ``<samples_root>/per_country/all/*.parquet`` — that's the
    legacy union parquet sitting in a per-country folder by mistake and
    must not be concatenated again (would double-count every row).
    """
    out: list[Path] = []
    base = samples_root / PER_COUNTRY_DIR
    if base.exists():
        for folder in sorted(base.iterdir()):
            if not folder.is_dir() or folder.name == "all":
                continue
            for p in folder.glob("*.parquet"):
                if p.name in {
                    f"{folder.name}_wikidata.parquet",  # legacy inside folder
                    f"{folder.name}.parquet",          # target naming
                }:
                    out.append(p)
    return out


def build_all_europe(
    samples_root: Path,
    *,
    out_path: Path | None = None,
) -> Path:
    """Build ``combined/all_europe.parquet`` by concatenating every per-country parquet.

    Returns the path written. Source parquets are read with the usual polars
    reader (works for both new ``<slug>.parquet`` and legacy
    ``<slug>_wikidata.parquet`` naming inside per_country/<slug>/).
    """
    out = out_path or combined_paths_for(samples_root).parquet
    out.parent.mkdir(parents=True, exist_ok=True)

    srcs = discover_country_parquets(samples_root)
    if not srcs:
        # Write an empty frame with the standard schema so the file exists.
        pl.DataFrame(schema={
            "osm_id": pl.Int64, "country": pl.String, "wikidata_qid": pl.String,
        }).write_parquet(out)
        return out

    df = pl.concat([pl.read_parquet(p) for p in srcs], how="diagonal_relaxed")
    df.write_parquet(out)
    return out


def build_sample_map(
    samples_root: Path,
    *,
    target_n: int = 4204,
    seed: int = 42,
    out_path: Path | None = None,
) -> Path:
    """Build a small JSONL (``sample/sample_map.jsonl``) for quick inspection.

    Samples ``target_n`` rows uniformly at random from the combined aggregate.
    One JSON record per line so the file stays stream-friendly.
    """
    out = out_path or sample_paths_for(samples_root).jsonl
    out.parent.mkdir(parents=True, exist_ok=True)

    combined_pq = combined_paths_for(samples_root).parquet
    if combined_pq.exists():
        df = pl.read_parquet(combined_pq)
    else:
        srcs = discover_country_parquets(samples_root)
        df = pl.concat([pl.read_parquet(p) for p in srcs], how="diagonal_relaxed") if srcs else pl.DataFrame()

    if df.height <= target_n:
        rows = df.to_dicts()
    else:
        rng = random.Random(seed)
        idx = sorted(rng.sample(range(df.height), target_n))
        rows = [df.row(i, named=True) for i in idx]

    with out.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    return out


__all__ = [
    "COMBINED_PARQUET_NAME",
    "build_all_europe",
    "build_sample_map",
    "discover_country_parquets",
]
