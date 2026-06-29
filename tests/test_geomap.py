"""Tests for the polygon-outline map builder.

Reads a parquet that already has ``geometry_wkt`` (the shape we ship to HF),
renders each polygon as a folium GeoJson (not just a centroid marker).
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.geomap import (
    build_polygon_map,
    parse_geometry_wkt,
)


def _matches_df() -> pl.DataFrame:
    return pl.DataFrame({
        "osm_id": [1, 2],
        "country": ["andorra", "estonia"],   # two countries -> two distinct colors
        "article_title": ["Lake Engolasters", "Kihnu"],
        "article_url": [
            "https://en.wikipedia.org/wiki/Lake_Engolasters",
            "https://en.wikipedia.org/wiki/Kihnu",
        ],
        "wikidata_qid": ["Q3215332", "Q1741199"],
        "article_description": ["Lake in Andorra", "Island in Estonia"],
        "geometry_wkt": [
            "POLYGON((1.5 42.5, 1.6 42.5, 1.6 42.6, 1.5 42.6, 1.5 42.5))",
            "MULTIPOLYGON(((24.0 58.0, 24.2 58.0, 24.2 58.2, 24.0 58.2, 24.0 58.0)))",
        ],
    })


# --- parse_geometry_wkt ----------------------------------------------------

def test_parse_geometry_wkt_handles_polygon() -> None:
    geom = parse_geometry_wkt("POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")
    assert geom.is_valid
    assert geom.area > 0


def test_parse_geometry_wkt_handles_multipolygon() -> None:
    geom = parse_geometry_wkt("MULTIPOLYGON(((0 0, 1 0, 1 1, 0 1, 0 0)))")
    assert geom.is_valid
    assert geom.area > 0


def test_parse_geometry_wkt_raises_on_invalid() -> None:
    with pytest.raises(ValueError):
        parse_geometry_wkt("not a wkt")


# --- build_polygon_map ---------------------------------------------------

def test_build_polygon_map_writes_html(tmp_path: Path) -> None:
    df = _matches_df()
    out = tmp_path / "map.html"
    build_polygon_map(df, out_path=out)
    assert out.exists()
    html = out.read_text()
    assert "<html" in html
    assert "folium" in html.lower()


def test_build_polygon_map_includes_article_titles_in_html(tmp_path: Path) -> None:
    df = _matches_df()
    out = tmp_path / "map.html"
    build_polygon_map(df, out_path=out)
    html = out.read_text()
    assert "Lake Engolasters" in html
    assert "Kihnu" in html


def test_build_polygon_map_renders_geojson_layer(tmp_path: Path) -> None:
    """Real polygons must be drawn, not just centroid markers."""
    df = _matches_df()
    out = tmp_path / "map.html"
    build_polygon_map(df, out_path=out)
    html = out.read_text()
    # folium's GeoJson embeds GeoJSON-formatted coordinates (no WKT text).
    # Verify the GeoJSON Polygon/MultiPolygon type signature is present
    # (folium emits with a space after the colon: '"type": "Polygon"').
    assert '"type": "Polygon"' in html or '"type": "MultiPolygon"' in html
    # We draw GeoJson polygons, not CircleMarker points
    assert "L.circleMarker" not in html and "L.marker(" not in html


def test_build_polygon_map_uses_distinct_colors(tmp_path: Path) -> None:
    df = _matches_df()
    out = tmp_path / "map.html"
    build_polygon_map(df, out_path=out)
    import re
    colors = set(re.findall(r"#[0-9a-fA-F]{6}", out.read_text()))
    assert len(colors) >= 2


def test_build_polygon_map_drops_rows_without_geometry(tmp_path: Path) -> None:
    df = pl.DataFrame({
        "osm_id": [1, 2],
        "country": ["andorra", "andorra"],
        "article_title": ["WithGeom", "NoGeom"],
        "geometry_wkt": ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))", None],
    })
    out = tmp_path / "map.html"
    build_polygon_map(df, out_path=out)
    html = out.read_text()
    assert "WithGeom" in html
    assert "NoGeom" not in html


def test_build_polygon_map_empty_df(tmp_path: Path) -> None:
    df = pl.DataFrame({
        "osm_id": pl.Series([], dtype=pl.Int64),
        "country": pl.Series([], dtype=pl.String),
        "article_title": pl.Series([], dtype=pl.String),
        "geometry_wkt": pl.Series([], dtype=pl.String),
    })
    out = tmp_path / "map.html"
    build_polygon_map(df, out_path=out)
    assert out.exists()


def test_build_polygon_map_handles_invalid_wkt_gracefully(tmp_path: Path) -> None:
    df = pl.DataFrame({
        "osm_id": [1, 2],
        "country": ["andorra", "andorra"],
        "article_title": ["Good", "BadGeom"],
        "geometry_wkt": ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))", "garbage"],
    })
    out = tmp_path / "map.html"
    build_polygon_map(df, out_path=out)  # should not raise
    html = out.read_text()
    assert "Good" in html