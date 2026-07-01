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

Public API (from each sub-module's own ``__all__``)
---------------------------------------------------
- :func:`build_map`
- :func:`build_polygon_map`
- :func:`render_map_png`
- :func:`parse_geometry_wkt`
"""
from __future__ import annotations

from . import geomap, map, render
from .._init_helpers import union_all
from .geomap import *  # noqa: F401, F403
from .map import *  # noqa: F401, F403
from .render import *  # noqa: F401, F403

__all__ = union_all(geomap, map, render)
