"""Wikidata-based polygon -> Wikipedia article matching (pure, no I/O).

The golden path: an OSM polygon may carry ``wikidata=Q<id>`` in its tags,
unambiguously identifying the entity. We resolve the QID via the Wikidata
API, then read the sitelinks to get the title of the matching Wikipedia
article in the requested language.

This module is *pure*: it has no network calls. The HTTP fetching lives
in :mod:`wikipedia.fetch` (see :func:`wikipedia.fetch.fetch_wikidata_sitelinks`
and :func:`wikipedia.fetch.fetch_sitelinks_batched`).
"""
from __future__ import annotations

import polars as pl

from .types import WikidataArticle

# Wiki Q-IDs are always "Q" + digits, e.g. "Q1011" (Vaduz).
_WIKIDATA_TAG_PREFIX = "wikidata="


def _sitelink_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"


def extract_wikidata_qid(tags: list[str] | None) -> str | None:
    """Return the Wikidata QID (e.g. ``Q1011``) from a polygon's tag list, if any."""
    if not tags:
        return None
    for t in tags:
        if t.startswith(_WIKIDATA_TAG_PREFIX):
            qid = t[len(_WIKIDATA_TAG_PREFIX):].strip()
            if qid.startswith("Q") and qid[1:].isdigit():
                return qid
            return None
    return None


def filter_polygons_with_wikidata(df: pl.DataFrame) -> pl.DataFrame:
    """Return only rows whose tags contain a well-formed ``wikidata=Q<id>``."""
    has_qid = df["tags"].list.eval(
        pl.element().str.starts_with(_WIKIDATA_TAG_PREFIX)
        & pl.element().str.slice(len(_WIKIDATA_TAG_PREFIX)).str.starts_with("Q")
        & pl.element().str.slice(len(_WIKIDATA_TAG_PREFIX) + 1).str.contains(r"^\d+$")
    ).list.any()
    return df.filter(has_qid)


def resolve_wikidata_to_article(
    qid: str,
    lang: str = "en",
    *,
    sitelinks: dict[str, dict[str, str]] | None = None,
) -> WikidataArticle | None:
    """Map a Wikidata QID to a Wikipedia article in ``lang``."""
    if sitelinks is None:
        raise RuntimeError(
            "sitelinks must be provided explicitly; use fetch_wikidata_sitelinks "
            "in production or pass a fixture in tests"
        )
    lang_key = f"{lang}wiki"
    if lang_key not in sitelinks:
        return None
    title = sitelinks[lang_key]["title"]
    return WikidataArticle(
        qid=qid,
        lang=lang,
        title=title,
        pageid=None,  # filled in later by summary fetch
        url=_sitelink_url(lang, title),
    )
