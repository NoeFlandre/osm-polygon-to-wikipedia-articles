"""Geographic visualization of matched polygons as an HTML map.

One CircleMarker per polygon, colored by country, with a popup linking to
the Wikipedia article.
"""
from __future__ import annotations

from pathlib import Path

import folium
import polars as pl

# ColorBrewer Set1-like palette (works well on the standard OSM basemap).
_PALETTE = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
    "#ffff33", "#a65628", "#f781bf", "#1b9e77", "#d95f02",
    "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d",
]


def build_map(
    df: pl.DataFrame,
    out_path: Path,
    *,
    tiles: str = "OpenStreetMap",
) -> Path:
    """Write a folium HTML map to ``out_path`` and return it.

    Markers are deliberately small + transparent so dense clusters stay
    readable. A two-column legend fits ~40 country names without dominating
    the map.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = df.filter(pl.col("centroid_lon").is_not_null() & pl.col("centroid_lat").is_not_null())
    if rows.height == 0:
        # Empty map centered on Europe; just write the skeleton.
        m = folium.Map(location=[50, 10], zoom_start=3, tiles=tiles)
        m.save(str(out_path))
        return out_path

    countries = sorted(rows["country"].unique().to_list())
    color_by_country = {c: _PALETTE[i % len(_PALETTE)] for i, c in enumerate(countries)}

    # Center the map on the median centroid (robust to outliers).
    mean_lat = float(rows["centroid_lat"].median())
    mean_lon = float(rows["centroid_lon"].median())

    m = folium.Map(location=[mean_lat, mean_lon], zoom_start=3, tiles=tiles)

    for r in rows.iter_rows(named=True):
        color = color_by_country[r["country"]]
        osm_type = r.get("osm_type") or ""
        osm_id = r.get("osm_id", "")
        popup_html = (
            f"<b>{r.get('article_title') or '(no title)'}</b><br>"
            f"<a href='{r.get('article_url', '')}' target='_blank'>Wikipedia</a><br>"
            f"country: {r['country']}<br>"
            f"OSM: {osm_type}/{osm_id}<br>"
            f"wikidata: {r.get('wikidata_qid', '')}"
        )
        folium.CircleMarker(
            location=[r["centroid_lat"], r["centroid_lon"]],
            radius=3,
            color=color,
            weight=0,
            fill=True,
            fill_color=color,
            fill_opacity=0.55,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=r.get("article_title") or f"{r['country']}/{r['osm_id']}",
        ).add_to(m)

    # Two-column legend so 40+ countries fit without covering the map.
    legend_items = []
    for i, (name, c) in enumerate(color_by_country.items()):
        col = i % 2
        legend_items.append(
            f"<span style='display:inline-block;width:50%;box-sizing:border-box;"
            f"padding:1px 4px 1px 0;vertical-align:top'>"
            f"<span style='display:inline-block;width:10px;height:10px;background:{c};"
            f"margin-right:5px;border-radius:50%;vertical-align:middle'></span>"
            f"<span style='vertical-align:middle;font-size:11px'>{name}</span></span>"
        )
    legend_html = (
        "<div style='position:fixed;bottom:14px;left:14px;z-index:9999;background:rgba(255,255,255,0.92);"
        "padding:8px 10px;border:1px solid #888;border-radius:4px;"
        f"font-family:sans-serif;max-width:280px'>"
        f"<div style='font-weight:600;font-size:12px;margin-bottom:4px'>"
        f"{len(countries)} countries &middot; {rows.height:,} polygons</div>"
        "<div>" + "".join(legend_items) + "</div></div>"
    )
    m.get_root().html.add_child(folium.Element(legend_html))

    m.save(str(out_path))
    return out_path