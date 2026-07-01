"""Canonical 4-subfolder dataset layout.

The published dataset is laid out as::

    samples/
    ├── README.md / manifest / metadata
    ├── per_country/<slug>/<slug>.parquet  (46 country folders)
    ├── combined/all_europe.parquet         (single union)
    ├── sample/sample_map.jsonl             (small JSONL)
    └── preview/map_preview.{png,html}      (static map)

This subpackage is split across several small files (one concern each):

- :mod:`._paths`            — path dataclasses + ``*_paths_for`` factories
- :mod:`._manifest`         — manifest / metadata / top-README writers
- :mod:`.full_layout`       — builders (build_all_europe, build_sample_map)
- :mod:`.migrate_full_layout` — copy legacy flat → new layout
- :mod:`.delete_legacy`     — safe-delete local duplicates
- :mod:`.delete_hf_duplicates` — safe-delete HF root duplicates
- :mod:`._slug_suffix`      — shared slug/suffix parser
- :mod:`._stats`            — shared aggregate-stats helper

Public API
----------
- Path dataclasses: :class:`RootPaths`, :class:`CountryPaths`,
  :class:`CombinedPaths`, :class:`SamplePaths`, :class:`PreviewPaths`.
- Builders: :func:`build_all_europe`, :func:`build_sample_map`,
  :func:`write_manifest_json`, :func:`build_metadata_json`,
  :func:`write_top_readme`.
- Migration: :func:`migrate_to_full_layout`.
- Safe deletion: :func:`safe_delete_audited`, :func:`classify_hf_file`,
  :func:`is_safe_to_delete_hf_root_file`.
"""
from __future__ import annotations

from ._manifest import build_metadata_json, write_manifest_json, write_top_readme
from ._paths import (
    CombinedPaths,
    CountryPaths,
    PreviewPaths,
    RootPaths,
    SamplePaths,
    combined_paths_for,
    country_paths_for,
    preview_paths_for,
    root_paths_for,
    sample_paths_for,
)
from ._slug_suffix import parse_hf_root_filename, parse_legacy_stem
from ._stats import aggregate_stats, slug_title
from .delete_hf_duplicates import (
    classify_hf_file,
    is_safe_to_delete_hf_root_file,
    survey_remotely_deleted_duplicates,
)
from .delete_legacy import safe_delete_audited
from .full_layout import (
    build_all_europe,
    build_sample_map,
    discover_country_parquets,
)
from .migrate_full_layout import migrate_to_full_layout

__all__ = [
    # path dataclasses
    "CombinedPaths",
    "CountryPaths",
    "PreviewPaths",
    "RootPaths",
    "SamplePaths",
    # path factories
    "combined_paths_for",
    "country_paths_for",
    "preview_paths_for",
    "root_paths_for",
    "sample_paths_for",
    # builders
    "build_all_europe",
    "build_metadata_json",
    "build_sample_map",
    "discover_country_parquets",
    "write_manifest_json",
    "write_top_readme",
    # migration
    "migrate_to_full_layout",
    # safe deletion
    "classify_hf_file",
    "is_safe_to_delete_hf_root_file",
    "safe_delete_audited",
    "survey_remotely_deleted_duplicates",
    # shared helpers
    "aggregate_stats",
    "parse_hf_root_filename",
    "parse_legacy_stem",
    "slug_title",
]
