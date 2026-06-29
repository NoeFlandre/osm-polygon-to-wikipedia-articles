"""Helpers for OSM polygon geometries (WKT).

The osm-polygon-selection dataset now includes a ``geometry_wkt`` column
with MULTIPOLYGON WKT strings. This module provides lightweight access to
the geometry column without pulling in a heavy GIS dependency at import time.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

# Data root for heavy files (PBFs, large intermediate parquets). Override with
# the OSM_DATA_ROOT env var; defaults to ./data so small samples work locally.
DATA_ROOT = Path(
    __import__("os").environ.get("OSM_DATA_ROOT", "data")
).resolve()


def resolve_data_path(*parts: str) -> Path:
    """Build a path under the project data root."""
    return DATA_ROOT.joinpath(*parts)


def ensure_geometry_column(df: pl.DataFrame) -> pl.DataFrame:
    """Return ``df`` guaranteed to have a ``geometry_wkt`` column (None if absent).

    The upstream dataset added ``geometry_wkt`` after the first release; older
    parquets won't have it. This helper normalizes that without failing.
    """
    if "geometry_wkt" in df.columns:
        return df
    return df.with_columns(pl.lit(None, dtype=pl.String).alias("geometry_wkt"))


def is_geometry_valid(wkt: str | None) -> bool:
    """Cheap sanity check that a geometry_wkt value looks like a polygon."""
    if not wkt:
        return False
    head = wkt.lstrip().upper()
    return head.startswith(("POLYGON", "MULTIPOLYGON"))