"""Tests for the dataset map builder."""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.visualization.map import build_map


def _matches_df() -> pl.DataFrame:
    return pl.DataFrame({
        "osm_id": [1, 2, 3],
        "osm_type": ["way", "relation", "way"],
        "country": ["monaco", "estonia", "malta"],
        "size_bin": ["small", "large", "small"],
        "centroid_lon": [7.426, 24.0, 14.32],
        "centroid_lat": [43.735, 58.13, 36.014],
        "wikidata_qid": ["Q7230673", "Q1741199", "Q828250"],
        "article_title": ["Port Hercules", "Kihnu", "Cominotto"],
        "article_url": [
            "https://en.wikipedia.org/wiki/Port_Hercules",
            "https://en.wikipedia.org/wiki/Kihnu",
            "https://en.wikipedia.org/wiki/Cominotto",
        ],
    })


def test_build_map_writes_html(tmp_path: Path) -> None:
    df = _matches_df()
    out = tmp_path / "map.html"
    build_map(df, out_path=out)
    assert out.exists()
    html = out.read_text()
    assert html.startswith("<!DOCTYPE html") or "<html" in html
    assert "folium" in html.lower()


def test_build_map_includes_all_polygons(tmp_path: Path) -> None:
    df = _matches_df()
    out = tmp_path / "map.html"
    build_map(df, out_path=out)
    html = out.read_text()
    for title in ("Port Hercules", "Kihnu", "Cominotto"):
        assert title in html


def test_build_map_uses_distinct_colors_per_country(tmp_path: Path) -> None:
    df = _matches_df()
    out = tmp_path / "map.html"
    build_map(df, out_path=out)
    html = out.read_text()
    # folium CircleMarker embeds fillColor; we expect 3 distinct colors
    import re
    colors = set(re.findall(r"fillColor[\"']?\s*[:=]\s*[\"']?(#[0-9a-fA-F]{6})", html))
    assert len(colors) >= 3


def test_build_map_drops_rows_without_lon_lat(tmp_path: Path) -> None:
    df = pl.DataFrame({
        "osm_id": [1, 2],
        "country": ["monaco", "estonia"],
        "article_title": ["Port Hercules", "Kihnu"],
        "centroid_lon": [7.426, None],
        "centroid_lat": [43.735, 58.13],
    })
    out = tmp_path / "map.html"
    build_map(df, out_path=out)
    html = out.read_text()
    assert "Port Hercules" in html
    assert "Kihnu" not in html


def test_build_map_handles_empty_df(tmp_path: Path) -> None:
    df = _matches_df().head(0)
    out = tmp_path / "map.html"
    build_map(df, out_path=out)
    assert out.exists()