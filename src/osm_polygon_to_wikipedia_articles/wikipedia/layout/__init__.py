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

Public API (from each sub-module's own ``__all__``)
---------------------------------------------------
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

from . import (
    _manifest,
    _paths,
    _slug_suffix,
    _stats,
    delete_hf_duplicates,
    delete_legacy,
    full_layout,
    migrate_full_layout,
)
from .._init_helpers import union_all
from ._manifest import *  # noqa: F401, F403
from ._paths import *  # noqa: F401, F403
from ._slug_suffix import *  # noqa: F401, F403
from ._stats import *  # noqa: F401, F403
from .delete_hf_duplicates import *  # noqa: F401, F403
from .delete_legacy import *  # noqa: F401, F403
from .full_layout import *  # noqa: F401, F403
from .migrate_full_layout import *  # noqa: F401, F403

__all__ = union_all(
    _manifest, _paths, _slug_suffix, _stats,
    delete_hf_duplicates, delete_legacy, full_layout, migrate_full_layout,
)
