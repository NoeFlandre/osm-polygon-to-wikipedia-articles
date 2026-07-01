"""Tests for the markdown-table helpers extracted from
``wikipedia.layout._readme_writers``.

Why
---
``_readme_writers.py`` had a duplicated markdown snippet in two
functions::

    "| Metric | Value |",
    "| ------ | ----- |",
    f"| Matched polygons | {s['matched']:,} |",
    f"| SVG thumbnails | {s['svg']:,} |",
    f"| Wikipedia body words | {s['words']:,} |",

…plus a duplicated "top-N contributors" table builder. The new
helpers in ``_readme_tables`` consolidate both patterns so the
writers read top-down instead of repeating six lines of boilerplate.
"""
from __future__ import annotations

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.layout._readme_tables import (
    headline_table,
    top_n_table,
)


# ---------------------------------------------------------------------------
# headline_table
# ---------------------------------------------------------------------------

def test_headline_table_renders_three_rows() -> None:
    md = headline_table({"matched": 12345, "svg": 67, "words": 987654})
    lines = md.splitlines()
    # 1 header row + 1 separator + 3 data rows = 5 lines
    assert len(lines) == 5
    assert lines[0] == "| Metric | Value |"
    assert lines[1] == "| ------ | ----- |"
    assert "| 12,345 |" in lines[2]   # matched
    assert "| 67 |" in lines[3]       # svg
    assert "| 987,654 |" in lines[4]  # words


def test_headline_table_thousands_separator() -> None:
    md = headline_table({"matched": 1_000_000, "svg": 0, "words": 42})
    assert "| 1,000,000 |" in md
    assert "| 0 |" in md
    assert "| 42 |" in md


def test_headline_table_labels_in_canonical_order() -> None:
    """The three rows must appear in the documented order: matched,
    svg, words — regardless of dict insertion order.
    """
    md = headline_table({"words": 1, "matched": 2, "svg": 3})
    rows = [l for l in md.splitlines() if l.startswith("| ")]
    assert "Matched polygons" in rows[2]
    assert "SVG thumbnails" in rows[3]
    assert "Wikipedia body words" in rows[4]


def test_headline_table_missing_keys_default_to_zero() -> None:
    """Defensive: if a stat is missing, render 0 instead of raising."""
    md = headline_table({})  # no keys at all
    assert "| 0 |" in md
    # all three rows still present
    rows = [l for l in md.splitlines() if l.startswith("| ") and "Metric" not in l
            and "---" not in l]
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# top_n_table
# ---------------------------------------------------------------------------

def test_top_n_table_three_columns() -> None:
    md = top_n_table(
        title="Top articles by polygon count",
        rows=[("Foo", 10), ("Bar", 5)],
        headers=("Article", "Polygons"),
    )
    lines = md.splitlines()
    assert lines[0] == "## Top articles by polygon count"
    assert lines[2] == "| Article | Polygons |"
    assert lines[3] == "| ------- | -------- |"
    assert "| Foo | 10 |" in lines[4]
    assert "| Bar | 5 |" in lines[5]


def test_top_n_table_thousands_separator_in_values() -> None:
    md = top_n_table(
        title="Top contributors",
        rows=[("italy", 12_345), ("france", 9_876)],
        headers=("Country", "Polygons"),
    )
    assert "| italy | 12,345 |" in md
    assert "| france | 9,876 |" in md


def test_top_n_table_empty_rows_just_returns_title_and_header() -> None:
    md = top_n_table(
        title="Top contributors",
        rows=[],
        headers=("Country", "Polygons"),
    )
    # header (title), blank, header row, separator — no data rows
    lines = md.splitlines()
    assert lines[0] == "## Top contributors"
    assert lines[2] == "| Country | Polygons |"
    assert lines[3] == "| ------- | -------- |"
    assert len(lines) == 4


def test_top_n_table_preserves_row_order() -> None:
    md = top_n_table(
        title="X",
        rows=[("c", 3), ("a", 1), ("b", 2)],
        headers=("Name", "Count"),
    )
    data_rows = [l for l in md.splitlines() if l.startswith("| ") and "---" not in l
                 and "Name" not in l]
    assert data_rows == ["| c | 3 |", "| a | 1 |", "| b | 2 |"]


def test_top_n_table_two_column_headers_required() -> None:
    with pytest.raises(ValueError):
        top_n_table(title="X", rows=[], headers=("OnlyOne",))
    with pytest.raises(ValueError):
        top_n_table(title="X", rows=[], headers=("A", "B", "C"))
