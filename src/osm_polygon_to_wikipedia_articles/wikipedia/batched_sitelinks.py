"""Back-compat shim. The real module now lives at
    osm_polygon_to_wikipedia_articles.wikipedia.fetch.batched_sitelinks

New code should import from the subpackage; this shim is kept so
legacy imports of the form ``from osm_polygon_to_wikipedia_articles
.wikipedia.batched_sitelinks import ...`` keep working without modification.
"""
from __future__ import annotations

from .fetch.batched_sitelinks import *  # noqa: F401, F403
