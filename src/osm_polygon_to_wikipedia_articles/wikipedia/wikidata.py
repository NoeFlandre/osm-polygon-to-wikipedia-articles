"""Back-compat shim. The real module now lives at
    osm_polygon_to_wikipedia_articles.wikipedia.pipeline.wikidata

New code should import from the subpackage; this shim is kept so
legacy imports of the form ``from osm_polygon_to_wikipedia_articles
.wikipedia.wikidata import ...`` keep working without modification.
"""
from __future__ import annotations

from .pipeline.wikidata import *  # noqa: F401, F403
