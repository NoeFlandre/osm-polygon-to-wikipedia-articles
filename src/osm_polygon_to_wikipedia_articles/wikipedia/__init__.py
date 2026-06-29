"""Wikipedia article matching layer (Stage 2).

Submodules:
    wikidata   -- QID extraction + sitelink resolution (pure)
    summary    -- REST /page/summary fetcher (HTTP)
    extracts   -- /w/api.php?prop=extracts plain-text fetcher (HTTP)
    match      -- orchestrator: applies all of the above to a polygon sample
"""
from .wikidata import (
    extract_wikidata_qid,
    filter_polygons_with_wikidata,
    resolve_wikidata_to_article,
)
from .types import ArticleSummary, MatchResult, WikidataArticle
from . import http_client, summary, extracts
from .match import match_polygons

__all__ = [
    "ArticleSummary",
    "MatchResult",
    "WikidataArticle",
    "extract_wikidata_qid",
    "filter_polygons_with_wikidata",
    "resolve_wikidata_to_article",
    "match_polygons",
    "http_client",
    "summary",
    "extracts",
]