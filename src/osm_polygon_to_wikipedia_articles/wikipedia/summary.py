"""Back-compat shim. The real module now lives at
    osm_polygon_to_wikipedia_articles.wikipedia.fetch.summary

New code should import from the subpackage; this shim is kept so
legacy imports of the form ``from osm_polygon_to_wikipedia_articles
.wikipedia.summary import ...`` keep working without modification.
"""
from __future__ import annotations

from .fetch.summary import *  # noqa: F401, F403
