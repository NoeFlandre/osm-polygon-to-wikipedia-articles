"""Back-compat shim. The real module now lives at
    osm_polygon_to_wikipedia_articles.wikipedia.visualization.render

New code should import from the subpackage; this shim is kept so
legacy imports of the form ``from osm_polygon_to_wikipedia_articles
.wikipedia.render import ...`` keep working without modification.
"""
from __future__ import annotations

from .visualization.render import *  # noqa: F401, F403
