"""Tests for the geometry helper module."""
from __future__ import annotations

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.polygons.geometry import (
    ensure_geometry_column,
    is_geometry_valid,
)


def test_ensure_geometry_column_passes_through_when_present() -> None:
    df = pl.DataFrame({"osm_id": [1], "geometry_wkt": ["POLYGON((1 2, 3 4, 1 2))"]})
    out = ensure_geometry_column(df)
    assert "geometry_wkt" in out.columns
    assert out["geometry_wkt"].to_list() == ["POLYGON((1 2, 3 4, 1 2))"]


def test_ensure_geometry_column_adds_null_when_absent() -> None:
    df = pl.DataFrame({"osm_id": [1, 2]})
    out = ensure_geometry_column(df)
    assert "geometry_wkt" in out.columns
    assert out["geometry_wkt"].null_count() == 2


def test_is_geometry_valid_polygon() -> None:
    assert is_geometry_valid("POLYGON((1 2, 3 4, 1 2))") is True
    assert is_geometry_valid("  polygon((1 2))") is True  # case + whitespace


def test_is_geometry_valid_multipolygon() -> None:
    assert is_geometry_valid("MULTIPOLYGON(((1 2, 3 4, 1 2)))") is True


def test_is_geometry_valid_rejects_non_polygon() -> None:
    assert is_geometry_valid("POINT(1 2)") is False
    assert is_geometry_valid("LINESTRING(1 2, 3 4)") is False
    assert is_geometry_valid("not geometry") is False


def test_is_geometry_valid_rejects_null_and_empty() -> None:
    assert is_geometry_valid(None) is False
    assert is_geometry_valid("") is False


def test_resolve_data_path_under_data_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OSM_DATA_ROOT", str(tmp_path))
    # reimport to pick up env var; the module reads it at import time
    import importlib
    from osm_polygon_to_wikipedia_articles.polygons import geometry
    importlib.reload(geometry)
    assert geometry.resolve_data_path("foo", "bar.parquet") == tmp_path / "foo" / "bar.parquet"