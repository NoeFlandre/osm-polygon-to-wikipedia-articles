"""Wikipedia article matching layer (Stage 2)."""
from .wikidata import (
    WikidataArticle,
    extract_wikidata_qid,
    filter_polygons_with_wikidata,
    resolve_wikidata_to_article,
)
from . import http_client

__all__ = [
    "WikidataArticle",
    "extract_wikidata_qid",
    "filter_polygons_with_wikidata",
    "resolve_wikidata_to_article",
    "http_client",
]