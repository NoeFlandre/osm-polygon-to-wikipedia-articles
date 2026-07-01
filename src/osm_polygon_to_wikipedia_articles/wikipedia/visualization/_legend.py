"""Legend HTML fragment shared by the folium map builders.

Each map overlays a small floating legend (country → colour swatch) so
the reader can decode which colour belongs to which country. The HTML
fragment is identical for the centroid-marker map and the polygon-
outline map; both used to embed their own copy inline.
"""
from __future__ import annotations


def build_legend_html(
    color_by_country: dict[str, str],
    *,
    total_polygons: int,
    title: str = "Countries",
) -> str:
    """Render the legend HTML for a folium map.

    Parameters
    ----------
    color_by_country:
        Mapping of country name → hex colour.
    total_polygons:
        Polygon count shown in the legend header (e.g. "46 countries ·
        32,124 polygons").
    title:
        Legend header text.
    """
    items_html: list[str] = []
    for i, (name, colour) in enumerate(color_by_country.items()):
        items_html.append(
            f"<span style='display:inline-block;width:50%;box-sizing:border-box;"
            f"padding:1px 4px 1px 0;vertical-align:top'>"
            f"<span style='display:inline-block;width:10px;height:10px;background:{colour};"
            f"margin-right:5px;border-radius:50%;vertical-align:middle'></span>"
            f"<span style='vertical-align:middle;font-size:11px'>{name}</span></span>"
        )
    n = len(color_by_country)
    return (
        "<div style='position:fixed;bottom:14px;left:14px;z-index:9999;"
        "background:rgba(255,255,255,0.92);padding:8px 10px;"
        "border:1px solid #888;border-radius:4px;font-family:sans-serif;max-width:280px'>"
        f"<div style='font-weight:600;font-size:12px;margin-bottom:4px'>"
        f"{title} &middot; {n} &middot; {total_polygons:,} polygons</div>"
        "<div>" + "".join(items_html) + "</div></div>"
    )


__all__ = ["build_legend_html"]
