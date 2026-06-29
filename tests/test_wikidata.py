"""Tests for Wikidata QID extraction and resolution."""
import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.wikidata import (
    extract_wikidata_qid,
    filter_polygons_with_wikidata,
    resolve_wikidata_to_article,
    WikidataArticle,
)


# --- extract_wikidata_qid --------------------------------------------------

def test_extract_returns_qid_when_tag_present() -> None:
    assert extract_wikidata_qid(["name=Foo", "wikidata=Q1011"]) == "Q1011"


def test_extract_returns_qid_when_alone() -> None:
    assert extract_wikidata_qid(["wikidata=Q1555"]) == "Q1555"


def test_extract_returns_none_when_absent() -> None:
    assert extract_wikidata_qid(["name=Foo", "landuse=forest"]) is None


def test_extract_returns_none_for_empty_list() -> None:
    assert extract_wikidata_qid([]) is None


def test_extract_returns_none_for_none_input() -> None:
    assert extract_wikidata_qid(None) is None


def test_extract_returns_none_for_malformed_qid() -> None:
    assert extract_wikidata_qid(["wikidata=1011"]) is None   # no Q prefix
    assert extract_wikidata_qid(["wikidata=Qabc"]) is None   # not digits
    assert extract_wikidata_qid(["wikidata="]) is None       # empty value


def test_extract_takes_first_wikidata_tag() -> None:
    assert extract_wikidata_qid(["wikidata=Q1", "wikidata=Q2"]) == "Q1"


# --- filter_polygons_with_wikidata ----------------------------------------

def _df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame({
        "osm_id": [r["osm_id"] for r in rows],
        "tags": [r["tags"] for r in rows],
    })


def test_filter_keeps_only_rows_with_valid_qid() -> None:
    df = _df([
        {"osm_id": 1, "tags": ["wikidata=Q1"]},
        {"osm_id": 2, "tags": ["name=Foo"]},
        {"osm_id": 3, "tags": ["wikidata=Q99", "landuse=forest"]},
        {"osm_id": 4, "tags": ["wikidata=bad"]},  # invalid — should be filtered out
    ])
    out = filter_polygons_with_wikidata(df)
    assert sorted(out["osm_id"].to_list()) == [1, 3]


def test_filter_empty_df_returns_empty() -> None:
    df = _df([{"osm_id": 1, "tags": ["landuse=forest"]}])
    out = filter_polygons_with_wikidata(df)
    assert out.height == 0


# --- resolve_wikidata_to_article ------------------------------------------

SITELINKS_VADUZ = {
    "enwiki": {"title": "Vaduz", "site": "enwiki"},
    "dewiki": {"title": "Vaduz", "site": "dewiki"},
    "frwiki": {"title": "Vaduz", "site": "frwiki"},
}


def test_resolve_returns_article_when_lang_present() -> None:
    art = resolve_wikidata_to_article("Q1011", lang="en", sitelinks=SITELINKS_VADUZ)
    assert isinstance(art, WikidataArticle)
    assert art.qid == "Q1011"
    assert art.title == "Vaduz"
    assert art.lang == "en"
    assert art.url == "https://en.wikipedia.org/wiki/Vaduz"


def test_resolve_returns_none_when_lang_missing() -> None:
    art = resolve_wikidata_to_article("Q1011", lang="ja", sitelinks=SITELINKS_VADUZ)
    assert art is None


def test_resolve_uses_different_lang() -> None:
    art = resolve_wikidata_to_article("Q1011", lang="de", sitelinks=SITELINKS_VADUZ)
    assert art is not None
    assert art.url == "https://de.wikipedia.org/wiki/Vaduz"


def test_resolve_requires_sitelinks_in_production() -> None:
    with pytest.raises(RuntimeError):
        resolve_wikidata_to_article("Q1011", lang="en")