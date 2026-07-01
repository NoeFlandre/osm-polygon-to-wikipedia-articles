"""Wikipedia article matching + dataset publication layer.

This package is organised into five subpackages, each with a single
responsibility:

- :mod:`.fetch`         — HTTP layer (Wikidata, Wikipedia REST, batched API)
- :mod:`.pipeline`      — pure logic + match orchestrator
- :mod:`.visualization` — folium maps + PNG renderer
- :mod:`.layout`        — canonical 4-subfolder dataset layout
- :mod:`.orchestration` — per-country end-to-end driver

For back-compat, the top-level package re-exports every public symbol
that scripts and tests historically imported directly from
``wikipedia``. New code is encouraged to import from the subpackage::

    from osm_polygon_to_wikipedia_articles.wikipedia.fetch import (
        fetch_wikidata_sitelinks,
    )
    from osm_polygon_to_wikipedia_articles.wikipedia.pipeline import (
        match_polygons,
    )

…but the legacy ``from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.match
import match_polygons`` continues to work.
"""
from __future__ import annotations

from . import fetch, layout, orchestration, pipeline, visualization
from ._init_helpers import union_all
from .fetch import *  # noqa: F401, F403
from .layout import *  # noqa: F401, F403
from .orchestration import *  # noqa: F401, F403
from .pipeline import *  # noqa: F401, F403
from .visualization import *  # noqa: F401, F403

__all__ = ["fetch", "layout", "orchestration", "pipeline", "visualization"]
__all__ += union_all(fetch, layout, orchestration, pipeline, visualization)
