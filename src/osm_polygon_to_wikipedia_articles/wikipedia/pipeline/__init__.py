"""Pure pipeline logic and the match orchestrator.

Everything in this subpackage is I/O-free: types are dataclasses,
``wikidata`` is a pure QID-extractor / filter / resolver, ``thumbnail``
is a pure URL inspector, and ``match`` is an orchestrator that takes
its HTTP fetchers as callables (see :mod:`wikipedia.fetch` for those).

Modules
-------
types
    ArticleSummary / MatchResult / WikidataArticle dataclasses.
wikidata
    ``extract_wikidata_qid``, ``filter_polygons_with_wikidata``,
    ``resolve_wikidata_to_article`` (all pure).
match
    ``match_polygons`` — the orchestrator that drives the per-polygon
    fetch/summary/extract sequence. Concurrent by default; resumable
    from a JSONL checkpoint.
thumbnail
    ``is_svg_url``, ``add_thumbnail_columns`` (rasterised-SVG aware).
union
    ``union_jsonls`` — concat per-country JSONLs into one parquet.

Public API (from each sub-module's own ``__all__``)
---------------------------------------------------
- :class:`MatchResult`, :class:`ArticleSummary`, :class:`WikidataArticle`
- :func:`extract_wikidata_qid`, :func:`filter_polygons_with_wikidata`,
  :func:`resolve_wikidata_to_article`
- :func:`match_polygons`
- :func:`is_svg_url`, :func:`add_thumbnail_columns`
- :func:`union_jsonls`, :func:`discover_per_country_jsonls`
"""
from __future__ import annotations

from . import match, thumbnail, types, union, wikidata
from .._init_helpers import union_all
from .match import *  # noqa: F401, F403
from .thumbnail import *  # noqa: F401, F403
from .types import *  # noqa: F401, F403
from .union import *  # noqa: F401, F403
from .wikidata import *  # noqa: F401, F403

__all__ = union_all(match, thumbnail, types, union, wikidata)
