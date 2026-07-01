"""Tests for the small shared helpers that several modules rely on.

These exist to break up the duplication that grew when the codebase
had 20 flat files: the colour palette, the legend HTML, the default
``_get_json`` body, the legacy-stem parser, and the aggregate-stats
calculator all appear in 2+ files. Centralising them under
``visualization/_palette``, ``visualization/_legend``,
``fetch/_helpers``, ``layout/_slug_suffix``, and ``layout/_stats``
means each consumer imports the same implementation.
"""
from __future__ import annotations

import polars as pl
import pytest

# --- visualization/_palette --------------------------------------------

def test_palette_is_a_non_empty_hex_list() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.visualization._palette import (
        PALETTE,
        color_by_country,
    )
    assert len(PALETTE) >= 15
    assert all(c.startswith("#") and len(c) == 7 for c in PALETTE)


def test_color_by_country_is_deterministic_and_cycles() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.visualization._palette import (
        PALETTE,
        color_by_country,
    )
    countries = ["albania", "andorra", "austria", "azores"]
    m1 = color_by_country(countries)
    m2 = color_by_country(list(reversed(countries)))  # order independent
    assert m1 == m2
    assert len(m1) == 4
    # After exhausting the palette, colours cycle. Use zero-padded names
    # so alphabetical sort = numerical order.
    n = len(PALETTE)
    big = color_by_country([f"c{i:03d}" for i in range(2 * n + 3)])
    assert big["c000"] == PALETTE[0]
    assert big["c001"] == PALETTE[1]
    assert big[f"c{n:03d}"] == PALETTE[0]  # wrapped back to start
    assert big[f"c{n + 2:03d}"] == PALETTE[2]  # continued cycle


# --- visualization/_legend ---------------------------------------------

def test_legend_html_lists_each_country_with_a_colour_swatch() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.visualization._legend import (
        build_legend_html,
    )
    html = build_legend_html(
        {"albania": "#e41a1c", "andorra": "#377eb8"},
        total_polygons=123,
    )
    assert "albania" in html
    assert "andorra" in html
    assert "#e41a1c" in html
    assert "123" in html  # polygon count


def test_legend_html_handles_empty_country_set() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.visualization._legend import (
        build_legend_html,
    )
    html = build_legend_html({}, total_polygons=0)
    assert "0" in html
    assert "<div" in html  # still renders a wrapper


# --- fetch/_helpers ---------------------------------------------------

def test_default_get_json_passes_accept_header() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.fetch import _helpers
    captured = {}

    def fake_client_get(url, *, headers):
        captured["url"] = url
        captured["headers"] = headers
        return {"ok": True}

    class _Stub:
        def get_json(self, url, *, headers):
            return fake_client_get(url, headers=headers)

        def close(self):
            pass

    _helpers._client = _Stub()
    out = _helpers.default_get_json("https://example.com/x", timeout=10)
    assert out == {"ok": True}
    assert captured["url"] == "https://example.com/x"
    assert captured["headers"]["Accept"] == "application/json"


def test_default_get_json_merges_extra_headers() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.fetch import _helpers
    captured = {}

    class _Stub:
        def get_json(self, url, *, headers):
            captured["headers"] = headers
            return {}

        def close(self):
            pass

    _helpers._client = _Stub()
    _helpers.default_get_json(
        "https://example.com/y",
        headers={"X-Custom": "1"},
    )
    assert captured["headers"]["Accept"] == "application/json"
    assert captured["headers"]["X-Custom"] == "1"


# --- layout/_slug_suffix ----------------------------------------------

def test_parse_legacy_stem_recognises_all_suffixes() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.layout._slug_suffix import (
        parse_legacy_stem,
    )
    assert parse_legacy_stem("poland_wikidata") == ("poland", "_wikidata")
    assert parse_legacy_stem("poland_wikidata_map") == ("poland", "_wikidata_map")
    assert parse_legacy_stem("poland_polygons_map") == ("poland", "_polygons_map")
    # Longest suffix wins (otherwise "poland_wikidata_map" would match
    # "_wikidata" first and yield slug="poland_wikidata_map").
    slug, _ = parse_legacy_stem("poland_wikidata_map")
    assert slug == "poland"


def test_parse_legacy_stem_returns_none_for_unknown() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.layout._slug_suffix import (
        parse_legacy_stem,
    )
    assert parse_legacy_stem("foo") == (None, None)
    assert parse_legacy_stem("") == (None, None)


def test_parse_hf_root_filename_handles_union_aggregates_first() -> None:
    """``all_wikidata.parquet`` MUST classify as the union, not a
    country parquet."""
    from osm_polygon_to_wikipedia_articles.wikipedia.layout._slug_suffix import (
        parse_hf_root_filename,
    )
    assert parse_hf_root_filename("all_wikidata.parquet") == (
        "all",
        "combined/all_europe.parquet",
    )
    assert parse_hf_root_filename("all_wikidata_map.png") == (
        "all",
        "preview/map_preview.png",
    )
    assert parse_hf_root_filename("map_preview.html") == (
        "all",
        "preview/map_preview.html",
    )


def test_parse_hf_root_filename_handles_country_files() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.layout._slug_suffix import (
        parse_hf_root_filename,
    )
    assert parse_hf_root_filename("poland_wikidata.parquet") == (
        "poland",
        "per_country/poland/poland.parquet",
    )
    assert parse_hf_root_filename("poland_wikidata.jsonl") == (
        "poland",
        "per_country/poland/poland_wikidata.jsonl",
    )
    assert parse_hf_root_filename("poland_wikidata_map.png") == (
        "poland",
        "per_country/poland/poland_wikidata_map.png",
    )
    assert parse_hf_root_filename("poland_polygons_map.html") == (
        "poland",
        "per_country/poland/poland_polygons_map.html",
    )


def test_parse_hf_root_filename_handles_bare_parquet_orphan() -> None:
    """``andorra.parquet`` is an orphan (no _wikidata suffix) that
    somehow ended up at the root; the parser routes it correctly."""
    from osm_polygon_to_wikipedia_articles.wikipedia.layout._slug_suffix import (
        parse_hf_root_filename,
    )
    assert parse_hf_root_filename("andorra.parquet") == (
        "andorra",
        "per_country/andorra/andorra.parquet",
    )


def test_parse_hf_root_filename_returns_none_for_unknown() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.layout._slug_suffix import (
        parse_hf_root_filename,
    )
    assert parse_hf_root_filename("foo.txt") is None
    assert parse_hf_root_filename("a_b_c.parquet") is None  # "_" in stem


# --- layout/_stats ---------------------------------------------------

def test_aggregate_stats_computes_matched_svg_words() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.layout._stats import (
        aggregate_stats,
    )
    df = pl.DataFrame({
        "country": ["albania", "andorra", "andorra"],
        "thumbnail_is_svg": [True, False, True],
        "article_body_text": ["a b c", None, "one two three four"],
    })
    s = aggregate_stats(df)
    assert s["matched"] == 3
    assert s["svg"] == 2
    assert s["words"] == 7  # 3 + 4 (None skipped)
    assert s["countries"] == ["albania", "andorra"]


def test_aggregate_stats_handles_missing_columns() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.layout._stats import (
        aggregate_stats,
    )
    df = pl.DataFrame({"country": ["a", "b"]})
    s = aggregate_stats(df)
    assert s["matched"] == 2
    assert s["svg"] == 0
    assert s["words"] == 0
    assert s["countries"] == ["a", "b"]


def test_slug_title_converts_dash_to_space_and_capitalises() -> None:
    from osm_polygon_to_wikipedia_articles.wikipedia.layout._stats import (
        slug_title,
    )
    assert slug_title("united-kingdom") == "United Kingdom"
    assert slug_title("albania") == "Albania"
    assert slug_title("czech-republic") == "Czech Republic"
