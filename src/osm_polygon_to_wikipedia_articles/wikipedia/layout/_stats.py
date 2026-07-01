"""Aggregate-stats and slug-title helpers shared by the layout code.

Both the per-country README writer and the combined README writer
needed the same ``matched / svg / words / countries`` tuple and the
same "poland → Poland, united-kingdom → United Kingdom" title rendering.
"""
from __future__ import annotations

import polars as pl


def aggregate_stats(df: pl.DataFrame) -> dict:
    """Return the headline numbers for any matched-polygons DataFrame.

    Always returns the same four keys so callers can ``format()`` safely::

        {"matched": int, "svg": int, "words": int, "countries": list[str]}

    Missing columns are tolerated: ``svg`` defaults to 0, ``words`` to 0,
    ``countries`` to ``[]``.
    """
    body = df["article_body_text"].to_list() if "article_body_text" in df.columns else []
    words = sum(len(t.split()) for t in body if t)
    svg = int(df["thumbnail_is_svg"].sum()) if "thumbnail_is_svg" in df.columns else 0
    countries = (
        sorted(df["country"].unique().to_list()) if "country" in df.columns else []
    )
    return {
        "matched": df.height,
        "svg": svg,
        "words": words,
        "countries": countries,
    }


def slug_title(slug: str) -> str:
    """``"united-kingdom"`` → ``"United Kingdom"`` (title-case on dashes)."""
    return slug.replace("-", " ").title()


__all__ = ["aggregate_stats", "slug_title"]
