"""Markdown table helpers for the layout README writers.

Centralises two markdown fragments that were previously duplicated
across ``write_per_country_readme`` and ``write_combined_readme``:

- the three-row "Matched / SVG / words" headline table
- the "Top N contributors" table

Both helpers are pure functions that take primitives and return a
string ending with a trailing newline so they can be appended to a
markdown buffer without extra blank-line management.
"""
from __future__ import annotations


# Canonical row order for :func:`headline_table`.  Listed in the
# same order they should appear in the rendered markdown.
_HEADLINE_ROWS: tuple[tuple[str, str], ...] = (
    ("Matched polygons", "matched"),
    ("SVG thumbnails", "svg"),
    ("Wikipedia body words", "words"),
)


def headline_table(stats: dict) -> str:
    """Render the three-row headline table used in every README.

    Parameters
    ----------
    stats
        Dict with optional ``matched``, ``svg``, ``words`` keys.
        Missing keys default to ``0``.

    Returns
    -------
    str
        Five lines: header, separator, three data rows. No trailing
        newline — callers are expected to add one.
    """
    lines = [
        "| Metric | Value |",
        "| ------ | ----- |",
    ]
    for label, key in _HEADLINE_ROWS:
        lines.append(f"| {label} | {stats.get(key, 0):,} |")
    return "\n".join(lines)


def top_n_table(
    *,
    title: str,
    rows: list[tuple[str, int]],
    headers: tuple[str, str],
) -> str:
    """Render a ``## title`` heading + two-column table.

    Parameters
    ----------
    title
        Markdown ``## `` heading (without the ``## `` prefix).
    rows
        Pre-sorted list of ``(label, count)`` pairs. The caller is
        responsible for sorting in the desired order.
    headers
        Two column headers. Anything other than length-2 raises
        :class:`ValueError`.

    Returns
    -------
    str
        ``## title`` + blank line + table. No trailing newline.
    """
    if len(headers) != 2:
        raise ValueError(
            f"top_n_table expects exactly 2 column headers, got {len(headers)}"
        )
    h_left, h_right = headers
    # Visual underline width: choose the wider of header / column-1 width.
    ul_left = max(len(h_left), 7)
    ul_right = max(len(h_right), 8)

    lines = [
        f"## {title}",
        "",
        f"| {h_left} | {h_right} |",
        f"| {'-' * ul_left} | {'-' * ul_right} |",
    ]
    for label, count in rows:
        lines.append(f"| {label} | {count:,} |")
    return "\n".join(lines)


__all__ = ["headline_table", "top_n_table"]
