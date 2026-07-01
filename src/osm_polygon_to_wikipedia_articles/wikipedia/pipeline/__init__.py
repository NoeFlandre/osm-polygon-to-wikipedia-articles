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

Public API
----------
- :class:`MatchResult`, :class:`ArticleSummary`, :class:`WikidataArticle`
- :func:`extract_wikidata_qid`, :func:`filter_polygons_with_wikidata`,
  :func:`resolve_wikidata_to_article`
- :func:`match_polygons`
- :func:`is_svg_url`, :func:`add_thumbnail_columns`
- :func:`union_jsonls`
"""
from __future__ import annotations

from .match import match_polygons
from .thumbnail import add_thumbnail_columns, is_svg_url
from .types import ArticleSummary, MatchResult, WikidataArticle
from .union import discover_per_country_jsonls, union_jsonls
from .wikidata import (
    extract_wikidata_qid,
    filter_polygons_with_wikidata,
    resolve_wikidata_to_article,
)

__all__ = [
    # types
    "ArticleSummary",
    "MatchResult",
    "WikidataArticle",
    # pure wikidata
    "extract_wikidata_qid",
    "filter_polygons_with_wikidata",
    "resolve_wikidata_to_article",
    # orchestrator
    "match_polygons",
    # thumbnail
    "add_thumbnail_columns",
    "is_svg_url",
    # union
    "discover_per_country_jsonls",
    "union_jsonls",
]
