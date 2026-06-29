"""Tests for Wikipedia article summary + body extraction."""
from __future__ import annotations

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.summary import (
    ArticleSummary,
    fetch_summary,
)
from osm_polygon_to_wikipedia_articles.wikipedia.extracts import (
    fetch_extract,
)


# --- fetch_summary -------------------------------------------------------

def test_fetch_summary_returns_parsed_fields() -> None:
    payload = {
        "title": "Kihnu",
        "pageid": 12345,
        "description": "Island in Estonia",
        "extract": "Kihnu is an island in Estonia.",
        "thumbnail": {"source": "https://upload.wikimedia.org/x/kihnu.jpg", "width": 320, "height": 240},
        "coordinates": {"lat": 58.13, "lon": 24.0},
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Kihnu"}},
    }

    def fake_get(url: str, timeout: int = 20) -> dict:
        assert "Kihnu" in url
        return payload

    s = fetch_summary(lang="en", title="Kihnu", _get=fake_get)
    assert isinstance(s, ArticleSummary)
    assert s.title == "Kihnu"
    assert s.pageid == 12345
    assert s.description == "Island in Estonia"
    assert s.extract == "Kihnu is an island in Estonia."
    assert s.thumbnail_url == "https://upload.wikimedia.org/x/kihnu.jpg"
    assert s.lat == 58.13
    assert s.lon == 24.0
    assert s.url == "https://en.wikipedia.org/wiki/Kihnu"


def test_fetch_summary_handles_missing_optional_fields() -> None:
    payload = {"title": "Foo", "pageid": 1, "extract": "Foo."}

    def fake_get(url: str, timeout: int = 20) -> dict:
        return payload

    s = fetch_summary(lang="en", title="Foo", _get=fake_get)
    assert s.description is None
    assert s.thumbnail_url is None
    assert s.lat is None
    assert s.lon is None
    assert s.url is None


def test_fetch_summary_returns_none_on_http_error() -> None:
    def fake_get(url: str, timeout: int = 20) -> dict:
        raise RuntimeError("network down")

    assert fetch_summary(lang="en", title="Foo", _get=fake_get) is None


# --- fetch_extract -------------------------------------------------------

def test_fetch_extract_returns_full_body() -> None:
    """The extract should contain the full body text, not truncated."""
    long_body = "Paragraph one.\n\n" + "Sentence after sentence. " * 200 + "\n\nLast paragraph."
    payload = {"query": {"pages": {"12345": {"extract": long_body}}}}

    def fake_get(url: str, timeout: int = 20) -> dict:
        assert "explaintext" in url
        return payload

    text = fetch_extract(lang="en", title="Kihnu", _get=fake_get)
    assert text == long_body
    assert text.count("Paragraph") >= 1
    # No truncation indicator: should contain the very last paragraph
    assert "Last paragraph." in text


def test_fetch_extract_returns_none_when_page_missing() -> None:
    payload = {"query": {"pages": {"-1": {"title": "Nope", "missing": ""}}}}

    def fake_get(url: str, timeout: int = 20) -> dict:
        return payload

    assert fetch_extract(lang="en", title="Nope", _get=fake_get) is None


def test_fetch_extract_returns_none_on_http_error() -> None:
    def fake_get(url: str, timeout: int = 20) -> dict:
        raise RuntimeError("network down")

    assert fetch_extract(lang="en", title="Foo", _get=fake_get) is None