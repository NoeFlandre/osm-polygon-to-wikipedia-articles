"""Geographic visualization of matched polygons as an HTML map.

One CircleMarker per polygon, colored by country, with a popup linking to
the Wikipedia article.
"""
from __future__ import annotations

from pathlib import Path

import folium
import polars as pl

from ._legend import build_legend_html
from ._palette import color_by_country


def _popup_html(r: dict) -> str:
    osm_type = r.get("osm_type") or ""
    osm_id = r.get("osm_id", "")
    return (
        f"<b>{r.get('article_title') or '(no title)'}</b><br>"
        f"<a href='{r.get('article_url', '')}' target='_blank'>Wikipedia</a><br>"
        f"country: {r['country']}<br>"
        f"OSM: {osm_type}/{osm_id}<br>"
        f"wikidata: {r.get('wikidata_qid', '')}"
    )


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

    rows = df.filter(
        pl.col("centroid_lon").is_not_null() & pl.col("centroid_lat").is_not_null()
    )
    if rows.height == 0:
        m = folium.Map(location=[50, 10], zoom_start=3, tiles=tiles)
        m.save(str(out_path))
        return out_path

    countries = rows["country"].unique().to_list()
    colour_map = color_by_country(countries)

    # Center the map on the median centroid (robust to outliers).
    mean_lat = float(rows["centroid_lat"].median())
    mean_lon = float(rows["centroid_lon"].median())

    m = folium.Map(location=[mean_lat, mean_lon], zoom_start=3, tiles=tiles)

    for r in rows.iter_rows(named=True):
        color = colour_map[r["country"]]
        folium.CircleMarker(
            location=[r["centroid_lat"], r["centroid_lon"]],
            radius=3,
            color=color,
            weight=0,
            fill=True,
            fill_color=color,
            fill_opacity=0.55,
            popup=folium.Popup(_popup_html(r), max_width=300),
            tooltip=r.get("article_title") or f"{r['country']}/{r['osm_id']}",
        ).add_to(m)

    m.get_root().html.add_child(
        folium.Element(build_legend_html(colour_map, total_polygons=rows.height))
    )
    m.save(str(out_path))
    return out_path


__all__ = ["build_map"]