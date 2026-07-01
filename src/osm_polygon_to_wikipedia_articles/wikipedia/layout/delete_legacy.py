"""Safe-deletion helpers used during the dataset-layout migration.

Mirrors ``migrate_full_layout`` *in reverse*: takes an already-canonical
layout and removes the legacy flat files at ``samples_root`` whose
content is byte-identical (or row-equivalent for the union parquet) to
a counterpart in ``per_country/<slug>/`` / ``combined/`` / ``preview/``.

Safety:
- Never deletes any file outside the surveyed-to-be-safe list.
- ``dry_run=True`` reports what *would* be deleted without touching disk.
- Idempotent: re-running removes nothing further.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

import polars as pl

from ._slug_suffix import parse_legacy_stem
from .full_layout import PER_COUNTRY_DIR

_SURVEY_EXTENSIONS = ("parquet", "jsonl", "html", "png")
_FLAT_GLOBS = ("*_wikidata.{ext}", "*_wikidata_map.{ext}", "*_polygons_map.{ext}")


def sha12(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def safe_delete(paths: Iterable[Path]) -> list[Path]:
    """Delete each path in ``paths`` if it exists. Skip silently otherwise.

    Returns the list of paths actually removed (useful for logging).
    """
    removed: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.exists():
            p.unlink()
            removed.append(p)
    return removed


def _canonic_for(samples_root: Path, slug: str, source_suffix: str, ext: str) -> Path | None:
    """Return the canonic counterpart of a legacy flat file (or None)."""
    if slug == "all":
        return None
    folder = samples_root / PER_COUNTRY_DIR / slug
    if source_suffix == "_wikidata" and ext == "parquet":
        return folder / f"{slug}.parquet"
    return folder / f"{slug}{source_suffix}.{ext}"


def _rowset_equals(a: Path, b: Path) -> bool:
    """Two parquets are equal if their ``(osm_id, country)`` row sets match."""
    try:
        x = pl.read_parquet(a).select(["osm_id", "country"]).sort(["country", "osm_id"])
        y = pl.read_parquet(b).select(["osm_id", "country"]).sort(["country", "osm_id"])
        return bool(x.equals(y))
    except Exception:
        return False


def _survey_country(samples_root: Path, slug: str, source_suffix: str, ext: str) -> tuple[Path, Path] | None:
    """Return ``(legacy, canonic)`` if their content matches, else ``None``."""
    legacy = samples_root / f"{slug}{source_suffix}.{ext}"
    canonic = _canonic_for(samples_root, slug, source_suffix, ext)
    if not legacy.exists() or not canonic or not canonic.exists():
        return None
    return legacy, canonic


def _survey_aggregates(samples_root: Path) -> list[tuple[Path, Path]]:
    """Survey the union parquet + union map png / html against their counterparts."""
    pairs: list[tuple[Path, Path]] = []
    for ext in ("png", "html"):
        legacy = samples_root / f"all_wikidata_map.{ext}"
        canonic = samples_root / "preview" / f"map_preview.{ext}"
        if legacy.exists() and canonic.exists() and sha12(legacy) == sha12(canonic):
            pairs.append((legacy, canonic))
    legacy = samples_root / "all_wikidata.parquet"
    canonic = samples_root / "combined" / "all_europe.parquet"
    if legacy.exists() and canonic.exists() and _rowset_equals(legacy, canonic):
        pairs.append((legacy, canonic))
    legacy = samples_root / "andorra.parquet"
    canonic = samples_root / PER_COUNTRY_DIR / "andorra" / "andorra.parquet"
    if legacy.exists() and canonic.exists() and sha12(legacy) == sha12(canonic):
        pairs.append((legacy, canonic))
    return pairs


def _survey_sample_match(samples_root: Path) -> list[tuple[Path, Path]]:
    """For every per-country ``<slug>_wikidata.{parquet,jsonl,html,png}`` file,
    find a sibling in ``per_country/<slug>/`` with the same content."""
    out: list[tuple[Path, Path]] = []
    for ext in _SURVEY_EXTENSIONS:
        for glob in _FLAT_GLOBS:
            for legacy in samples_root.glob(glob.format(ext=ext)):
                slug, source_suffix = parse_legacy_stem(legacy.stem)
                if slug is None or source_suffix is None:
                    continue
                pair = _survey_country(samples_root, slug, source_suffix, ext)
                if pair is None or sha12(pair[0]) != sha12(pair[1]):
                    continue
                out.append(pair)
    return out


def safe_delete_audited(samples_root: Path, *, dry_run: bool = False) -> list[Path]:
    """Survey the canonical layout, collect safe-to-delete legacy paths,
    optionally delete them. Idempotent.
    """
    samples_root = Path(samples_root)
    pairs: list[tuple[Path, Path]] = []
    pairs.extend(_survey_sample_match(samples_root))
    pairs.extend(_survey_aggregates(samples_root))

    legacy_paths = sorted({p[0] for p in pairs})
    if dry_run:
        return list(legacy_paths)
    return safe_delete(legacy_paths)


__all__ = [
    "safe_delete",
    "safe_delete_audited",
    "sha12",
]

