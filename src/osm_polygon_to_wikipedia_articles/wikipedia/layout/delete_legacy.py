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

from .full_layout import PER_COUNTRY_DIR

_SURVEY_EXTENSIONS = ("parquet", "jsonl", "html", "png")


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


def _slug_from_stem(stem: str) -> tuple[str | None, str | None]:
    """Map a flat-file stem to ``(slug, source_suffix)`` (or ``None``s)."""
    for suffix in ("_wikidata_map", "_polygons_map", "_wikidata"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)], suffix
    return None, None


# --- Survey rules: which (legacy_path, canonic_path) pairs are safe? ------


def _survey_country(samples_root: Path, slug: str, source_suffix: str, ext: str) -> tuple[Path, Path] | None:
    """Return ``(legacy, canonic)`` if their content matches, else ``None``."""
    legacy = samples_root / f"{slug}{source_suffix}.{ext}"
    if not legacy.exists() or slug == "all":
        return None
    if source_suffix == "_wikidata":
        if ext == "parquet":
            canonic = samples_root / PER_COUNTRY_DIR / slug / f"{slug}.parquet"
        else:
            canonic = samples_root / PER_COUNTRY_DIR / slug / f"{slug}{source_suffix}.{ext}"
    else:
        canonic = samples_root / PER_COUNTRY_DIR / slug / f"{slug}{source_suffix}.{ext}"
    if not canonic.exists():
        return None
    return legacy, canonic


def _survey_aggregates(samples_root: Path) -> list[tuple[Path, Path]]:
    """Survey the union parquet + union map png / html against their counterparts."""
    pairs: list[tuple[Path, Path]] = []
    # Union map png/html → preview/map_preview.{png,html}
    for ext in ("png", "html"):
        legacy = samples_root / f"all_wikidata_map.{ext}"
        canonic = samples_root / "preview" / f"map_preview.{ext}"
        if legacy.exists() and canonic.exists() and sha12(legacy) == sha12(canonic):
            pairs.append((legacy, canonic))
    # Union parquet → combined/all_europe.parquet (row-equivalent, not byte)
    legacy = samples_root / "all_wikidata.parquet"
    canonic = samples_root / "combined" / "all_europe.parquet"
    if legacy.exists() and canonic.exists():
        try:
            a = pl.read_parquet(legacy).select(["osm_id", "country"]).sort(["country", "osm_id"])
            b = pl.read_parquet(canonic).select(["osm_id", "country"]).sort(["country", "osm_id"])
            if a.equals(b):
                pairs.append((legacy, canonic))
        except Exception:
            pass
    # Orphan andorra.parquet at root → per_country/andorra/andorra.parquet
    legacy = samples_root / "andorra.parquet"
    canonic = samples_root / PER_COUNTRY_DIR / "andorra" / "andorra.parquet"
    if legacy.exists() and canonic.exists() and sha12(legacy) == sha12(canonic):
        pairs.append((legacy, canonic))
    return pairs


def _survey_sample_match(samples_root: Path) -> list[tuple[Path, Path]]:
    """For every per-country ``<slug>_wikidata.{parquet,jsonl,html,png}`` file,
    find a sibling in ``per_country/<slug>/`` with the same content (when one
    exists)."""
    out: list[tuple[Path, Path]] = []
    for ext in _SURVEY_EXTENSIONS:
        for legacy in samples_root.glob(f"*_wikidata.{ext}"):
            stem = legacy.stem
            slug, source_suffix = _slug_from_stem(stem)
            if slug is None or source_suffix is None:
                continue
            pair = _survey_country(samples_root, slug, source_suffix, ext)
            if pair is None:
                continue
            if sha12(pair[0]) == sha12(pair[1]):
                out.append(pair)
        for legacy in samples_root.glob(f"*_wikidata_map.{ext}"):
            stem = legacy.stem
            slug, source_suffix = _slug_from_stem(stem)
            if slug is None or source_suffix is None:
                continue
            pair = _survey_country(samples_root, slug, source_suffix, ext)
            if pair is None:
                continue
            if sha12(pair[0]) == sha12(pair[1]):
                out.append(pair)
        for legacy in samples_root.glob(f"*_polygons_map.{ext}"):
            stem = legacy.stem
            slug, source_suffix = _slug_from_stem(stem)
            if slug is None or source_suffix is None:
                continue
            pair = _survey_country(samples_root, slug, source_suffix, ext)
            if pair is None:
                continue
            if sha12(pair[0]) == sha12(pair[1]):
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
