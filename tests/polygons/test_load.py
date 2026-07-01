"""Tests for polygon loading from the osm-polygon-selection HF dataset."""
from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.polygons import (
    list_countries,
    load_country,
    sample_polygons,
    build_sample,
)


def _make_fixture(tmp_path: Path, slug: str = "albania") -> Path:
    """Download a small slice of the real dataset for offline use.

    The source dataset migrated to the canonical 4-subfolder layout, so the
    parquet for a country lives at ``per_country/<slug>/<slug>.parquet``.
    """
    path = tmp_path / f"{slug}.parquet"
    df = pl.read_parquet(
        f"hf://datasets/NoeFlandre/osm-polygon-selection/per_country/{slug}/{slug}.parquet"
    ).head(20)
    df.write_parquet(path)
    return path


def test_list_countries_returns_sorted_unique_slugs() -> None:
    countries = list_countries(repo_id="NoeFlandre/osm-polygon-selection")
    assert isinstance(countries, list)
    assert countries == sorted(countries)
    assert len(countries) > 0
    assert all(isinstance(c, str) and c and " " not in c for c in countries)


def test_list_countries_includes_liechtenstein() -> None:
    countries = list_countries(repo_id="NoeFlandre/osm-polygon-selection")
    assert "liechtenstein" in countries


def test_load_country_returns_expected_schema(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    df = load_country(slug="albania", repo_id="NoeFlandre/osm-polygon-selection", local_path=fixture)
    expected_cols = {
        "osm_id", "osm_type", "centroid_lon", "centroid_lat",
        "area_km2", "tags", "continent", "size_bin", "country",
    }
    assert expected_cols.issubset(set(df.columns))
    assert df.height > 0


def test_load_country_country_column_matches_slug(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    df = load_country(slug="albania", repo_id="NoeFlandre/osm-polygon-selection", local_path=fixture)
    assert df["country"].unique().to_list() == ["albania"]


def test_load_country_raises_on_missing_local_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_country(slug="albania", repo_id="NoeFlandre/osm-polygon-selection", local_path=tmp_path / "nope.parquet")


def test_load_country_raises_on_missing_slug() -> None:
    with pytest.raises(FileNotFoundError):
        load_country(slug="atlantis", repo_id="NoeFlandre/osm-polygon-selection")