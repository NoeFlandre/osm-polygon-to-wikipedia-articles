"""Tests for polygon loading from the osm-polygon-selection HF dataset."""
from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.load import list_countries, load_country

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def fixture_parquet() -> Path:
    """Write a small real-schema parquet fixture once for these tests."""
    path = FIXTURE_DIR / "liechtenstein.parquet"
    if not path.exists():
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        df = pl.read_parquet("hf://datasets/NoeFlandre/osm-polygon-selection/liechtenstein.parquet").head(20)
        df.write_parquet(path)
    return path


def test_list_countries_returns_sorted_unique_slugs() -> None:
    countries = list_countries(repo_id="NoeFlandre/osm-polygon-selection")
    assert isinstance(countries, list)
    assert countries == sorted(countries)
    assert len(countries) > 0
    # every entry is a non-empty slug-shaped string
    assert all(isinstance(c, str) and c and " " not in c for c in countries)


def test_list_countries_includes_liechtenstein() -> None:
    countries = list_countries(repo_id="NoeFlandre/osm-polygon-selection")
    assert "liechtenstein" in countries


def test_load_country_returns_expected_schema(fixture_parquet: Path) -> None:
    # we exercise the loader against the local fixture, not the network
    df = load_country(slug="liechtenstein", repo_id="NoeFlandre/osm-polygon-selection", local_path=fixture_parquet)
    expected_cols = {
        "osm_id", "osm_type", "centroid_lon", "centroid_lat",
        "area_km2", "tags", "continent", "size_bin", "country",
    }
    assert expected_cols.issubset(set(df.columns))
    assert df.height > 0


def test_load_country_country_column_matches_slug(fixture_parquet: Path) -> None:
    df = load_country(slug="liechtenstein", repo_id="NoeFlandre/osm-polygon-selection", local_path=fixture_parquet)
    assert df["country"].unique().to_list() == ["liechtenstein"]


def test_load_country_raises_on_missing_slug() -> None:
    with pytest.raises(FileNotFoundError):
        load_country(slug="atlantis", repo_id="NoeFlandre/osm-polygon-selection")