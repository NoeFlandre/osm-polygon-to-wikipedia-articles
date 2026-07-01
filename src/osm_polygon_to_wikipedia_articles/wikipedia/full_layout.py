"""Canonical target layout for the published dataset.

Target structure (replacing the flat ``data/samples/``):

    data/samples/                            ← root
    ├── README.md
    ├── manifest                              # NEW: structural fingerprint
    ├── metadata                              # NEW: schema docs
    ├── per_country/                          # one folder per country
    │   ├── README.md
    │   ├── poland/
    │   │   ├── README.md
    │   │   └── poland.parquet
    │   └── ...
    ├── combined/                             # single union parquet
    │   ├── README.md
    │   └── all_europe.parquet
    ├── sample/                               # small JSONL for inspection
    │   ├── README.md
    │   └── sample_map.jsonl
    └── preview/                              # static map for quick eyeballing
        ├── README.md
        └── map_preview.png
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import polars as pl

PER_COUNTRY_DIR = "per_country"
COMBINED_DIR = "combined"
SAMPLE_DIR = "sample"
PREVIEW_DIR = "preview"

# Filename conventions
COMBINED_PARQUET_NAME = "all_europe.parquet"
SAMPLE_JSONL_NAME = "sample_map.jsonl"
PREVIEW_PNG_NAME = "map_preview.png"


# --- Path dataclasses ----------------------------------------------------


@dataclass(frozen=True)
class RootPaths:
    readme: Path
    manifest: Path
    metadata: Path


@dataclass(frozen=True)
class CountryPaths:
    folder: Path
    parquet: Path
    readme: Path


@dataclass(frozen=True)
class CombinedPaths:
    parquet: Path
    readme: Path


@dataclass(frozen=True)
class SamplePaths:
    jsonl: Path
    readme: Path


@dataclass(frozen=True)
class PreviewPaths:
    png: Path
    readme: Path


def root_paths_for(samples_root: Path) -> RootPaths:
    return RootPaths(
        readme=samples_root / "README.md",
        manifest=samples_root / "manifest",
        metadata=samples_root / "metadata",
    )


def country_paths_for(samples_root: Path, country_slug: str) -> CountryPaths:
    folder = samples_root / PER_COUNTRY_DIR / country_slug
    return CountryPaths(
        folder=folder,
        parquet=folder / f"{country_slug}.parquet",
        readme=folder / "README.md",
    )


def combined_paths_for(samples_root: Path) -> CombinedPaths:
    folder = samples_root / COMBINED_DIR
    return CombinedPaths(
        parquet=folder / COMBINED_PARQUET_NAME,
        readme=folder / "README.md",
    )


def sample_paths_for(samples_root: Path) -> SamplePaths:
    folder = samples_root / SAMPLE_DIR
    return SamplePaths(
        jsonl=folder / SAMPLE_JSONL_NAME,
        readme=folder / "README.md",
    )


def preview_paths_for(samples_root: Path) -> PreviewPaths:
    folder = samples_root / PREVIEW_DIR
    return PreviewPaths(
        png=folder / PREVIEW_PNG_NAME,
        readme=folder / "README.md",
    )


# --- manifest / metadata writers -----------------------------------------


def write_manifest_json(
    samples_root: Path,
    *,
    countries: Iterable[str],
    combined_rows: int,
    combined_words: int,
    sample_rows: int,
    svg_count: int,
) -> Path:
    """Write the structural fingerprint of the dataset.

    The ``manifest`` is JSON-shaped plain text describing the dataset at the
    highest level (countries, totals, sample size) so consumers can decide at
    a glance whether the snapshot matches their expectations.
    """
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


# --- builders ------------------------------------------------------------


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
            if not folder.is_dir():
                continue
            if folder.name == "all":
                # Skip the legacy union parquet sitting in per_country/all/.
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
    paths = combined_paths_for(samples_root)
    out = out_path or paths.parquet
    out.parent.mkdir(parents=True, exist_ok=True)

    srcs = discover_country_parquets(samples_root)
    if not srcs:
        # Write an empty frame with the standard schema so the file exists.
        pl.DataFrame(schema={
            "osm_id": pl.Int64, "country": pl.String, "wikidata_qid": pl.String,
        }).write_parquet(out)
        return out

    frames = [pl.read_parquet(p) for p in srcs]
    df = pl.concat(frames, how="diagonal_relaxed")
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
    paths = sample_paths_for(samples_root)
    out = out_path or paths.jsonl
    out.parent.mkdir(parents=True, exist_ok=True)

    combined_pq = combined_paths_for(samples_root).parquet
    if combined_pq.exists():
        df = pl.read_parquet(combined_pq)
    else:
        srcs = discover_country_parquets(samples_root)
        frames = [pl.read_parquet(p) for p in srcs]
        df = pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

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


# --- top readme ----------------------------------------------------------


def write_top_readme(
    samples_root: Path,
    *,
    countries: int,
    total_rows: int,
    total_words: int,
) -> Path:
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
