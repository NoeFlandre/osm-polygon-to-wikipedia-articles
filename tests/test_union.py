"""Tests for the per-country JSONL union."""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.union import (
    SAMPLES_DIR,
    discover_per_country_jsonls,
    union_jsonls,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _match_record(country: str, osm_id: int, title: str, body: str = "body") -> dict:
    return {
        "osm_id": osm_id, "osm_type": "way", "country": country, "size_bin": "small",
        "centroid_lon": 1.5, "centroid_lat": 42.5,
        "wikidata_qid": f"Q{osm_id}", "sitelinks_count": 1,
        "article_title": title, "article_lang": "en", "article_url": f"https://x/{title}",
        "match_status": "matched", "article_description": None, "article_extract_short": None,
        "article_thumbnail_url": None, "article_lat": None, "article_lon": None,
        "article_pageid": 1, "article_body_text": body,
    }


def test_union_combines_all_country_jsonls(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "andorra_wikidata.jsonl", [_match_record("andorra", 1, "Kihnu")])
    _write_jsonl(tmp_path / "monaco_wikidata.jsonl", [_match_record("monaco", 2, "Port Hercules")])

    out = tmp_path / "all.parquet"
    df = union_jsonls(
        [tmp_path / "andorra_wikidata.jsonl", tmp_path / "monaco_wikidata.jsonl"],
        out,
    )
    assert out.exists()
    assert df.height == 2
    assert df["country"].n_unique() == 2


def test_union_skips_blank_lines(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "x_wikidata.jsonl", [_match_record("andorra", 1, "Foo")])
    p = tmp_path / "x_wikidata.jsonl"
    with p.open("a") as f:
        f.write("\n\n")

    df = union_jsonls([p], tmp_path / "out.parquet")
    assert df.height == 1


def test_discover_finds_per_country_files(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "andorra_wikidata.jsonl", [])
    _write_jsonl(tmp_path / "monaco_wikidata.jsonl", [])
    _write_jsonl(tmp_path / "all_wikidata.jsonl", [])  # should be excluded
    _write_jsonl(tmp_path / "README.md", [])  # unrelated, should be excluded

    found = discover_per_country_jsonls(tmp_path)
    names = [p.name for p in found]
    assert "andorra_wikidata.jsonl" in names
    assert "monaco_wikidata.jsonl" in names
    assert "all_wikidata.jsonl" not in names
    assert "README.md" not in names


def test_union_library_handles_empty_input(tmp_path: Path) -> None:
    """No JSONLs -> empty DataFrame."""
    df = union_jsonls([], tmp_path / "out.parquet")
    assert df.height == 0


def test_discover_returns_empty_when_no_files(tmp_path: Path) -> None:
    assert discover_per_country_jsonls(tmp_path) == []