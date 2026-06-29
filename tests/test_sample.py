"""Tests for polygon sampling."""
import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.sample import sample_polygons, build_sample


def _make_df(n: int = 100, size_bins: tuple[str, ...] = ("small", "medium", "large"), country: str = "synthetic") -> pl.DataFrame:
    """Build a synthetic polygon df with the schema load_country produces."""
    rng = range(n)
    return pl.DataFrame({
        "osm_id": list(rng),
        "osm_type": ["way"] * n,
        "centroid_lon": [i * 0.01 for i in rng],
        "centroid_lat": [i * 0.01 for i in rng],
        "area_km2": [0.5 + i * 0.01 for i in rng],
        "tags": [["landuse=forest"]] * n,
        "continent": ["Europe"] * n,
        "size_bin": [size_bins[i % len(size_bins)] for i in rng],
        "country": [country] * n,
    })


def test_sample_polygons_returns_at_most_n() -> None:
    df = _make_df(100)
    out = sample_polygons(df, n=10, seed=0)
    assert out.height == 10
    assert out.height <= 10


def test_sample_polygons_is_deterministic_with_seed() -> None:
    df = _make_df(100)
    a = sample_polygons(df, n=10, seed=42)
    b = sample_polygons(df, n=10, seed=42)
    assert a["osm_id"].to_list() == b["osm_id"].to_list()


def test_sample_polygons_changes_with_seed() -> None:
    df = _make_df(100)
    a = sample_polygons(df, n=10, seed=0)
    b = sample_polygons(df, n=10, seed=1)
    assert a["osm_id"].to_list() != b["osm_id"].to_list()


def test_sample_polygons_n_equals_df_height_returns_all() -> None:
    df = _make_df(5)
    out = sample_polygons(df, n=5, seed=0)
    assert out.height == 5


def test_sample_polygons_no_duplicate_ids() -> None:
    df = _make_df(100)
    out = sample_polygons(df, n=20, seed=0)
    assert out["osm_id"].n_unique() == out.height


def test_sample_polygons_stratified_preserves_size_bin_distribution() -> None:
    df = _make_df(90, size_bins=("small", "medium", "large"))
    out = sample_polygons(df, n=9, seed=0, stratify_by="size_bin")
    counts = out.group_by("size_bin").len().sort("size_bin")
    # 30 per bin in source, n=9 across 3 bins -> 3 per bin
    assert counts["len"].to_list() == [3, 3, 3]


def test_build_sample_combines_multiple_countries(tmp_path) -> None:
    fixtures = {
                "liechtenstein": _make_df(50, country="liechtenstein"),
                "monaco": _make_df(50, country="monaco"),
            }
    out_path = tmp_path / "sample.parquet"
    df = build_sample(
        countries=["liechtenstein", "monaco"],
        n_per_country=5,
        seed=0,
        out_path=out_path,
        fixtures=fixtures,
    )
    assert out_path.exists()
    assert df["country"].n_unique() == 2
    assert df.height == 10  # 5 + 5
    assert df.group_by("country").len().sort("country")["len"].to_list() == [5, 5]