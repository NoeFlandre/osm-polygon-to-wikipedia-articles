"""Tests for thumbnail-URL metadata columns."""
from __future__ import annotations

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.thumbnail import (
    add_thumbnail_columns,
    is_svg_url,
)


# --- pure unit tests ------------------------------------------------------

def test_is_svg_url_true() -> None:
    assert is_svg_url("https://upload.wikimedia.org/wikipedia/commons/a/ab/Foo.svg") is True
    assert is_svg_url("https://example.invalid/logo.svg?width=240") is True
    assert is_svg_url("https://example.invalid/logo.SVG") is True  # case insensitive
    # Wikimedia serves rasterised SVGs as `.svg.png` — these are still SVGs by origin
    assert is_svg_url("https://upload.wikimedia.org/wikipedia/commons/thumb/foo.svg/240px-foo.svg.png") is True
    assert is_svg_url("https://upload.wikimedia.org/wikipedia/commons/thumb/bar.SVG/240px-bar.SVG.PNG") is True


def test_is_svg_url_false() -> None:
    assert is_svg_url("https://upload.wikimedia.org/thumb/Foo.jpg/240px-Foo.jpg") is False
    assert is_svg_url("https://example.invalid/img.png") is False
    assert is_svg_url("https://example.invalid/img.jpg") is False
    assert is_svg_url("https://example.invalid/img.webp") is False
    assert is_svg_url(None) is False
    assert is_svg_url("") is False


def test_is_svg_url_ignores_extensionless() -> None:
    """URLs with no extension are not SVG."""
    assert is_svg_url("https://example.invalid/noext") is False


# --- column-addition tests ------------------------------------------------

def test_add_thumbnail_columns_adds_svg_flag() -> None:
    df = pl.DataFrame(
        {
            "article_thumbnail_url": [
                "https://upload.wikimedia.org/wikipedia/commons/a/ab/Foo.svg",
                "https://upload.wikimedia.org/thumb/Foo.jpg/240px-Foo.jpg",
                None,
                "",
                "https://example.invalid/logo.SVG",
                "https://upload.wikimedia.org/wikipedia/commons/thumb/Llogara.svg.png",
            ],
            "article_title": ["a", "b", "c", "d", "e", "f"],
        }
    )
    out = add_thumbnail_columns(df)
    assert "thumbnail_is_svg" in out.columns
    assert out["thumbnail_is_svg"].to_list() == [True, False, False, False, True, True]
    # Original dataframe should be unaffected (immutable schema)
    assert "thumbnail_is_svg" not in df.columns


def test_add_thumbnail_columns_preserves_existing() -> None:
    """Adding the column must not drop any existing columns."""
    df = pl.DataFrame(
        {
            "article_thumbnail_url": ["https://x.svg"],
            "article_title": ["Foo"],
            "country": ["poland"],
            "article_body_text": ["some body"],
        }
    )
    out = add_thumbnail_columns(df)
    for col in df.columns:
        assert col in out.columns
    assert "thumbnail_is_svg" in out.columns


def test_add_thumbnail_columns_idempotent() -> None:
    """Calling twice produces the same result (deterministic)."""
    df = pl.DataFrame({"article_thumbnail_url": ["https://x.svg", "https://y.jpg"]})
    a = add_thumbnail_columns(df)
    b = add_thumbnail_columns(df)
    assert a["thumbnail_is_svg"].to_list() == b["thumbnail_is_svg"].to_list()
