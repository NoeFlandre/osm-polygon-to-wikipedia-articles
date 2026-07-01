"""Canonical 4-subfolder dataset layout.

The published dataset is laid out as::

    samples/
    ├── README.md / manifest / metadata
    ├── per_country/<slug>/<slug>.parquet  (46 country folders)
    ├── combined/all_europe.parquet         (single union)
    ├── sample/sample_map.jsonl             (small JSONL)
    └── preview/map_preview.{png,html}      (static map)

This subpackage owns:

- the path dataclasses (:class:`RootPaths`, :class:`CountryPaths`, …)
  and ``*_paths_for`` factories;
- the builders (:func:`build_all_europe`, :func:`build_sample_map`,
  :func:`write_manifest_json`, :func:`build_metadata_json`);
- the legacy-flat migration (:func:`migrate_to_full_layout`);
- safe-deletion helpers — both local (:func:`safe_delete_audited`)
  and HF root (:func:`classify_hf_file` + :func:`is_safe_to_delete_hf_root_file`).

Public API
----------
- Path dataclasses: :class:`RootPaths`, :class:`CountryPaths`,
  :class:`CombinedPaths`, :class:`SamplePaths`, :class:`PreviewPaths`.
- Builders: :func:`build_all_europe`, :func:`build_sample_map`,
  :func:`write_manifest_json`, :func:`build_metadata_json`.
- Migration: :func:`migrate_to_full_layout`.
- Safe deletion: :func:`safe_delete_audited`, :func:`classify_hf_file`,
  :func:`is_safe_to_delete_hf_root_file`.
"""
from __future__ import annotations

from .delete_hf_duplicates import (
    classify_hf_file,
    is_safe_to_delete_hf_root_file,
    survey_remotely_deleted_duplicates,
)
from .delete_legacy import safe_delete_audited
from .full_layout import (
    CombinedPaths,
    CountryPaths,
    PreviewPaths,
    RootPaths,
    SamplePaths,
    build_all_europe,
    build_metadata_json,
    build_sample_map,
    combined_paths_for,
    country_paths_for,
    preview_paths_for,
    root_paths_for,
    sample_paths_for,
    write_manifest_json,
    write_top_readme,
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
    "write_manifest_json",
    "write_top_readme",
    # migration
    "migrate_to_full_layout",
    # safe deletion
    "classify_hf_file",
    "is_safe_to_delete_hf_root_file",
    "safe_delete_audited",
    "survey_remotely_deleted_duplicates",
]
