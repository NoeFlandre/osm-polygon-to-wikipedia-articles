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

_LEGACY_FILE_NAMES = {"README.md", "manifest", "metadata", ".gitattributes"}


def _slug_and_destination(filename: str) -> tuple[str, str] | None:
    """Return ``(slug, canonic_HF_path)`` for a known legacy root file.

    Returns ``None`` for files we don't have a canonical mapping for
    (these should be left untouched).
    """
    name = filename
    # Union aggregate MUST be checked BEFORE the suffix-based rules,
    # otherwise ``all_wikidata.parquet`` would resolve to
    # ``per_country/all/all.parquet``.
    if name == "all_wikidata.parquet":
        return "all", "combined/all_europe.parquet"
    if name in {"all_wikidata_map.png", "all_wikidata_map.html"}:
        ext = name.rsplit(".", 1)[1]
        return "all", f"preview/map_preview.{ext}"
    # map_preview.{png,html} pushed to root earlier — also exists at preview/
    if name in {"map_preview.png", "map_preview.html"}:
        return "all", f"preview/{name}"
    # <slug>_polygons_map.{html,png}
    for ext in ("html", "png"):
        if name.endswith(f"_polygons_map.{ext}"):
            slug = name[: -len(f"_polygons_map.{ext}")]
            return slug, f"per_country/{slug}/{slug}_polygons_map.{ext}"
    # <slug>_wikidata_map.{html,png}
    for ext in ("html", "png"):
        if name.endswith(f"_wikidata_map.{ext}"):
            slug = name[: -len(f"_wikidata_map.{ext}")]
            return slug, f"per_country/{slug}/{slug}_wikidata_map.{ext}"
    # <slug>_wikidata.jsonl
    if name.endswith("_wikidata.jsonl"):
        slug = name[: -len("_wikidata.jsonl")]
        return slug, f"per_country/{slug}/{slug}_wikidata.jsonl"
    # <slug>_wikidata.parquet  →  per_country/<slug>/<slug>.parquet
    if name.endswith("_wikidata.parquet"):
        slug = name[: -len("_wikidata.parquet")]
        return slug, f"per_country/{slug}/{slug}.parquet"
    # andorra.parquet (orphan, no _wikidata suffix)
    if name.endswith(".parquet") and "_" not in name and "/" not in name:
        slug = name[: -len(".parquet")]
        return slug, f"per_country/{slug}/{slug}.parquet"
    return None


def classify_hf_file(filename: str) -> tuple[str, str] | None:
    """Public alias of ``_slug_and_destination``."""
    if filename in _LEGACY_FILE_NAMES:
        return None
    return _slug_and_destination(filename)


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
    is_parquet_a = root_path.read_bytes()[:4] == b"PAR1"
    is_parquet_b = canonic_path.read_bytes()[:4] == b"PAR1"
    if is_parquet_a and is_parquet_b:
        try:
            a = pl.read_parquet(root_path).select(["osm_id", "country"]).sort(["country", "osm_id"])
            b = pl.read_parquet(canonic_path).select(["osm_id", "country"]).sort(["country", "osm_id"])
            return bool(a.equals(b))
        except Exception:
            return False
    # byte equality for everything else
    return hashlib.sha256(root_path.read_bytes()).hexdigest() == hashlib.sha256(canonic_path.read_bytes()).hexdigest()


def survey_remotely_deleted_duplicates(
    hf_files: list[str],
    local_root_files: set[str],
) -> list[str]:
    """Return HF root paths that are classified as duplicated and locally absent.

    The "locally absent" check ensures we don't recommend deletion of files
    whose canonical copy hasn't been verified on disk.
    """
    out: list[str] = []
    for f in hf_files:
        if "/" in f:
            continue  # only root files
        if f in local_root_files:
            continue  # local has the file → can't be sure HF has a duplicate
        slug_canon = classify_hf_file(f)
        if slug_canon is None:
            continue
        slug, canonic_hf_path = slug_canon
        out.append((f, canonic_hf_path))
    return [(hf_f, canonic) for hf_f, canonic in out]
