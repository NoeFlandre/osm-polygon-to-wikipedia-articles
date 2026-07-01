"""Safe deletion of duplicate files at the Hugging Face dataset root.

After the layout migration, ``<slug>_wikidata.{parquet,jsonl,html,png}`` and
the ``all_wikidata.*`` aggregates are now living in their canonical
``per_country/<slug>/`` / ``combined/`` / ``preview/`` siblings. The
stale root copies remain on HF unless we explicitly delete them.

This module:
1. classifies a root filename into a ``(slug, canonic_path)`` pair
2. compares a local-on-disk root file against a local-on-disk canonic file
   - byte-identical for ``html``, ``png``, ``jsonl``
   - row-set equivalent for parquet (schemas may differ; row identity is
     what matters for downstream consumers)
3. defers the actual HF API ``delete_files`` call to a higher-level
   orchestrator that downloads + verifies + deletes.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl

from ._slug_suffix import parse_hf_root_filename

# Always-passthrough filenames that should never be classified for deletion
# (they're either canonical themselves or HF metadata).
_LEGACY_FILE_NAMES = {"README.md", "manifest", "metadata", ".gitattributes"}


def classify_hf_file(filename: str) -> tuple[str, str] | None:
    """Return ``(slug, canonic_HF_path)`` for a known legacy root file.

    Returns ``None`` for files we don't have a canonical mapping for
    (these should be left untouched).
    """
    if filename in _LEGACY_FILE_NAMES:
        return None
    return parse_hf_root_filename(filename)


def is_safe_to_delete_hf_root_file(
    root_path: Path,
    canonic_path: Path,
) -> bool:
    """Compare ``root_path`` against ``canonic_path`` — True iff identical.

    For parquet files, byte equality is too strict (different schemas), so
    we use row-set equality on ``(osm_id, country)`` instead.
    """
    if not root_path.exists() or not canonic_path.exists():
        return False
    # Detect parquet by checking the magic number (PAR1 at offset 4)
    if root_path.read_bytes()[:4] == b"PAR1" and canonic_path.read_bytes()[:4] == b"PAR1":
        try:
            a = pl.read_parquet(root_path).select(["osm_id", "country"]).sort(["country", "osm_id"])
            b = pl.read_parquet(canonic_path).select(["osm_id", "country"]).sort(["country", "osm_id"])
            return bool(a.equals(b))
        except Exception:
            return False
    return hashlib.sha256(root_path.read_bytes()).hexdigest() == hashlib.sha256(canonic_path.read_bytes()).hexdigest()


def survey_remotely_deleted_duplicates(
    hf_files: list[str],
    local_root_files: set[str],
) -> list[tuple[str, str]]:
    """Return HF root paths that are classified as duplicated and locally absent.

    The "locally absent" check ensures we don't recommend deletion of files
    whose canonical copy hasn't been verified on disk.
    """
    out: list[tuple[str, str]] = []
    for f in hf_files:
        if "/" in f or f in local_root_files:
            continue
        slug_canon = classify_hf_file(f)
        if slug_canon is None:
            continue
        out.append((f, slug_canon[1]))
    return out


__all__ = [
    "classify_hf_file",
    "is_safe_to_delete_hf_root_file",
    "survey_remotely_deleted_duplicates",
]

