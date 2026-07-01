"""Polygon-outline map: read geometry_wkt from a matches parquet and draw the
actual polygon outlines (not centroid markers) on a folium map.

For inspection of an already-shipped parquet.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import folium
import polars as pl
from shapely import wkt as shapely_wkt
from shapely.geometry.base import BaseGeometry

# Distinct fill colors for polygon outlines; reused from the marker map.
_PALETTE = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00",
    "#ffff33", "#a65628", "#f781bf", "#1b9e77", "#d95f02",
    "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d",
]


def parse_geometry_wkt(wkt: str) -> BaseGeometry:
    """Parse a WKT string to a Shapely geometry. Raises ``ValueError`` on bad input."""
    try:
        return shapely_wkt.loads(wkt)
    except Exception as exc:
        raise ValueError(f"invalid WKT: {wkt[:60]!r}") from exc


def _iter_valid_rows(df: pl.DataFrame) -> Iterable[dict]:
    """Yield only rows with a usable ``geometry_wkt``."""
    if "geometry_wkt" not in df.columns:
        return
    for row in df.iter_rows(named=True):
        wkt = row.get("geometry_wkt")
        if not wkt:
            continue
        try:
            geom = parse_geometry_wkt(wkt)
        except ValueError:
            continue
        if not geom.is_valid or geom.is_empty:
            continue
        yield {**row, "_geometry": geom}


def _popup_html(row: dict) -> str:
    title = row.get("article_title") or "(no title)"
    url = row.get("article_url") or ""
    country = row.get("country") or ""
    osm_id = row.get("osm_id", "")
    osm_type = row.get("osm_type") or ""
    qid = row.get("wikidata_qid") or ""
    desc = row.get("article_description") or ""

    parts = [
        f"<b>{title}</b>",
        f"<a href='{url}' target='_blank'>Wikipedia</a>" if url else "",
        f"<br><i>{desc}</i>" if desc else "",
        f"<br>country: {country}",
        f"<br>OSM: {osm_type}/{osm_id}",
        f"<br>wikidata: {qid}",
    ]
    return "".join(p for p in parts if p)


def build_polygon_map(
    df: pl.DataFrame,
    out_path: Path,
    *,
    tiles: str = "OpenStreetMap",
) -> Path:
    """Write a folium HTML map with one GeoJson polygon per row to ``out_path``."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = list(_iter_valid_rows(df))
    if not rows:
        # empty skeleton centered on Europe
        m = folium.Map(location=[42.5, 1.5], zoom_start=4, tiles=tiles)
        m.save(str(out_path))
        return out_path

    # Color by country
    countries = sorted({r["country"] for r in rows if r.get("country")})
    color_by_country = {c: _PALETTE[i % len(_PALETTE)] for i, c in enumerate(countries)}

    # Center map on the union of all geometries' bounds
    from shapely.ops import unary_union
    union = unary_union([r["_geometry"] for r in rows])
    minx, miny, maxx, maxy = union.bounds
    center_lat = (miny + maxy) / 2
    center_lon = (minx + maxx) / 2

    m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles=tiles)

    # One GeoJson layer per country so each gets a single color and legend entry
    for country in countries:
        country_rows = [r for r in rows if r.get("country") == country]
        color = color_by_country[country]
        features = [
            {
                "type": "Feature",
                "properties": {
                    "title": r.get("article_title") or "",
                    "popup": _popup_html(r),
                    "tooltip": r.get("article_title") or "",
                },
                "geometry": r["_geometry"].__geo_interface__,
            }
            for r in country_rows
        ]
        gj = folium.GeoJson(
            {"type": "FeatureCollection", "features": features},
            name=country,
            style_function=lambda _feat, c=color: {
                "fillColor": c, "color": c, "weight": 2, "fillOpacity": 0.45,
            },
            highlight_function=lambda _feat: {"weight": 4, "fillOpacity": 0.7},
        )
        # Per-feature popup: read the HTML we stashed in feature.properties.popup
        folium.GeoJsonPopup(
            fields=["popup"],
            labels=False,
            localize=True,
            parse_html=False,
        ).add_to(gj)
        folium.GeoJsonTooltip(
            fields=["title"],
            aliases=["article"],
            localize=True,
        ).add_to(gj)
        gj.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Legend
    legend_items = "".join(
        f"<li><span style='display:inline-block;width:14px;height:14px;background:{c};"
        f"opacity:0.6;border:1px solid {c};margin-right:6px'></span>{name}</li>"
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