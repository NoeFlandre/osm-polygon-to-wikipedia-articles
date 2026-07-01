"""Country colour palette shared by every folium map.

ColorBrewer Set1 (works well on the standard OSM basemap).
Exposed as :data:`PALETTE` and :func:`color_by_country`.
"""
from __future__ import annotations

PALETTE: list[str] = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
    "#ffff33", "#a65628", "#f781bf", "#1b9e77", "#d95f02",
    "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d",
]


def color_by_country(countries: list[str]) -> dict[str, str]:
    """Map each country to a stable colour from :data:`PALETTE`.

    The mapping is order-independent (sorts the input first) so two
    callers passing the same set of countries get the same colours.
    After the palette is exhausted colours cycle.
    """
    out: dict[str, str] = {}
    for i, c in enumerate(sorted(countries)):
        out[c] = PALETTE[i % len(PALETTE)]
    return out


__all__ = ["PALETTE", "color_by_country"]
