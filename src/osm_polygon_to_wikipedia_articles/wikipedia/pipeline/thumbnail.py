"""Pure helpers for thumbnail URL inspection + columns.

Used to flag whether each polygon's Wikipedia thumbnail is an SVG
(typical of logos, banners, icons — usually bad when the goal is "natural
image of place") vs a raster image (JPEG/PNG/WEBP — typically a real photo).
"""
from __future__ import annotations

import polars as pl

THUMBNAIL_IS_SVG = "thumbnail_is_svg"


def is_svg_url(url: str | None) -> bool:
    """Return True iff ``url`` was originally an SVG.

    Wikipedia's thumbnail service rasterises SVGs to PNG but keeps the
    ``.svg`` token in the filename — e.g. ``Llogara.svg/240px-Llogara.svg.png``.
    We treat any of these as "originated from SVG" since:

    * ``.svg`` extension on the leaf
    * ``.svg.png`` (Wikimedia's rasterised-SVG thumbnail convention)
    * ``.svg.<anything>``

    Query strings and URL fragments are stripped first.
    """
    if not url:
        return False
    leaf = url.split("?", 1)[0].split("#", 1)[0].rsplit("/", 1)[-1].lower()
    if not leaf:
        return False
    # Split on dots: if any segment equals 'svg' (case-insensitive), it's an SVG
    parts = leaf.split(".")
    return any(p == "svg" for p in parts)


def add_thumbnail_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Return a copy of ``df`` with the thumbnail-flag columns attached.

    Adds:
      - ``thumbnail_is_svg`` (bool): True for SVG thumbnails.

    Null thumbnails are flagged as False (i.e. "not a known SVG image").
    The function is idempotent (calling twice is harmless: the existing
    column gets overwritten deterministically).
    """
    # Use a Python list comprehension so we have full control over None
    # handling (polars `map_elements` would propagate nulls as nulls).
    svg_flags = [is_svg_url(u) for u in df["article_thumbnail_url"].to_list()]
    return df.with_columns(
        pl.Series(THUMBNAIL_IS_SVG, svg_flags, dtype=pl.Boolean)
    )


__all__ = ["add_thumbnail_columns", "is_svg_url"]
