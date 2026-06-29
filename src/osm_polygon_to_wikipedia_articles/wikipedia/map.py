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
    """Write a folium HTML map to ``out_path`` and return it."""
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

    # Center the map on the mean of all centroids.
    mean_lat = float(rows["centroid_lat"].mean())
    mean_lon = float(rows["centroid_lon"].mean())

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
            radius=8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=r.get("article_title") or f"{r['country']}/{r['osm_id']}",
        ).add_to(m)

    # Legend
    legend_items = "".join(
        f"<li><span style='display:inline-block;width:12px;height:12px;background:{c};margin-right:6px;border-radius:2px'></span>{name}</li>"
        for name, c in color_by_country.items()
    )
    legend_html = (
        f"<div style='position:fixed;bottom:20px;left:20px;z-index:9999;background:white;"
        f"padding:10px;border:2px solid #444;border-radius:4px;font-family:sans-serif;font-size:12px'>"
        f"<b>Countries</b><ul style='list-style:none;padding:0;margin:6px 0 0'>{legend_items}</ul></div>"
    )
    m.get_root().html.add_child(folium.Element(legend_html))

    m.save(str(out_path))
    return out_path