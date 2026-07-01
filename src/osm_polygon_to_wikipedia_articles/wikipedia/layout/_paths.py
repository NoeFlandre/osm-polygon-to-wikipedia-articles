"""Path dataclasses + factories for the canonical dataset layout.

Frozen dataclasses that bundle related paths so callers don't have to
hand-roll ``samples_root / 'per_country' / slug / 'X.parquet'`` everywhere.
Each dataclass has a matching ``*_paths_for(samples_root, ...)`` factory.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PER_COUNTRY_DIR = "per_country"
COMBINED_DIR = "combined"
SAMPLE_DIR = "sample"
PREVIEW_DIR = "preview"

# Filename conventions
COMBINED_PARQUET_NAME = "all_europe.parquet"
SAMPLE_JSONL_NAME = "sample_map.jsonl"
PREVIEW_PNG_NAME = "map_preview.png"


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


__all__ = [
    "COMBINED_DIR",
    "COMBINED_PARQUET_NAME",
    "CombinedPaths",
    "CountryPaths",
    "PER_COUNTRY_DIR",
    "PREVIEW_DIR",
    "PREVIEW_PNG_NAME",
    "PreviewPaths",
    "RootPaths",
    "SAMPLE_DIR",
    "SAMPLE_JSONL_NAME",
    "SamplePaths",
    "combined_paths_for",
    "country_paths_for",
    "preview_paths_for",
    "root_paths_for",
    "sample_paths_for",
]
