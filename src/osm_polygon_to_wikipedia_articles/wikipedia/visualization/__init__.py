"""Geographic visualisation: folium HTML maps + headless-Chrome PNG renderer.

Three layers, increasing fidelity:

- :mod:`map`   — one CircleMarker per polygon, colored by country.
  The lightweight, all-countries overview map (the one that ships in
  the dataset's ``preview/`` and ``combined/`` folders).
- :mod:`geomap` — one GeoJson polygon per row, drawing the real
  outlines from the ``geometry_wkt`` column. Heavier — for inspection
  of a single country's actual polygon shapes.
- :mod:`render` — renders any of the above HTMLs to PNG via
  Playwright/Chromium.

Public API
----------
- :func:`build_map`
- :func:`build_polygon_map`
- :func:`render_map_png`
"""
from __future__ import annotations

from .geomap import build_polygon_map, parse_geometry_wkt
from .map import build_map
from .render import render_map_png

__all__ = [
    "build_map",
    "build_polygon_map",
    "parse_geometry_wkt",
    "render_map_png",
]
