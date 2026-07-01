"""Tests for the per-country batch processor."""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.orchestration.process_countries import (
    discover_countries_with_wikidata,
    plan_country_run,
    validate_country_outputs,
)


# --- discover_countries_with_wikidata -------------------------------------

def _fake_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)


def test_discover_finds_countries_with_wikidata(tmp_path: Path) -> None:
    base = tmp_path / "dataset"
    _fake_parquet(base / "andorra.parquet", [{"osm_id": 1, "tags": ["wikidata=Q1"]}])
    _fake_parquet(base / "monaco.parquet", [{"osm_id": 2, "tags": []}])  # no wikidata -> skip
    _fake_parquet(base / "malta.parquet", [{"osm_id": 3, "tags": ["wikidata=Q3", "name=Foo"]}])

    found = discover_countries_with_wikidata(base)
    assert found == ["andorra", "malta"]


def test_discover_empty_dir(tmp_path: Path) -> None:
    base = tmp_path / "empty"
    base.mkdir()
    assert discover_countries_with_wikidata(base) == []


# --- plan_country_run -----------------------------------------------------

def test_plan_country_run_returns_paths(tmp_path: Path) -> None:
    plan = plan_country_run(country="malta", data_root=tmp_path, samples_root=tmp_path)
    assert plan.country == "malta"
    assert plan.source == tmp_path / "malta.parquet"
    assert plan.match_parquet == tmp_path / "malta_wikidata.parquet"
    assert plan.match_jsonl == tmp_path / "malta_wikidata.jsonl"
    assert plan.match_map_html == tmp_path / "malta_wikidata_map.html"
    assert plan.match_map_png == tmp_path / "malta_wikidata_map.png"


def test_plan_country_run_is_path_only(tmp_path: Path) -> None:
    """The plan should describe I/O targets only — no network or processing."""
    plan = plan_country_run(country="malta", data_root=tmp_path, samples_root=tmp_path)
    assert plan.source.exists() is False  # no IO happened


# --- validate_country_outputs --------------------------------------------

def test_validate_passes_for_good_outputs(tmp_path: Path) -> None:
    plan = plan_country_run(country="malta", data_root=tmp_path, samples_root=tmp_path)
    plan.match_parquet.parent.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame({
        "osm_id": [1, 2],
        "country": ["malta", "malta"],
        "wikidata_qid": ["Q1", "Q2"],
        "article_title": ["Foo", "Bar"],
        "article_body_text": ["a" * 100, "b" * 100],
        "geometry_wkt": ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                         "POLYGON((2 2, 3 2, 3 3, 2 3, 2 2))"],
    })
    df.write_parquet(plan.match_parquet)
    plan.match_jsonl.write_text('{"osm_id":1}\n{"osm_id":2}\n')
    plan.match_map_html.write_text("<html></html>")

    report = validate_country_outputs(plan)
    assert report.ok
    assert report.n_rows == 2
    assert report.geometry_wkt_missing == 0
    assert report.articles_with_body == 2
    assert report.jsonl_count == 2
    assert report.map_html_size > 0


def test_validate_fails_when_parquet_missing(tmp_path: Path) -> None:
    plan = plan_country_run(country="malta", data_root=tmp_path, samples_root=tmp_path)
    report = validate_country_outputs(plan)
    assert not report.ok
    assert "parquet" in report.errors[0].lower()


def test_validate_fails_on_geometry_missing(tmp_path: Path) -> None:
    plan = plan_country_run(country="malta", data_root=tmp_path, samples_root=tmp_path)
    plan.match_parquet.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "osm_id": [1],
        "country": ["malta"],
        "wikidata_qid": ["Q1"],
        "article_title": ["Foo"],
        "article_body_text": ["x" * 100],
        # geometry_wkt column absent — should fail validation
    }).write_parquet(plan.match_parquet)
    plan.match_jsonl.write_text('{"osm_id":1}\n')

    report = validate_country_outputs(plan)
    assert not report.ok
    assert any("geometry" in e.lower() for e in report.errors)


def test_validate_fails_when_jsonl_count_mismatches(tmp_path: Path) -> None:
    plan = plan_country_run(country="malta", data_root=tmp_path, samples_root=tmp_path)
    plan.match_parquet.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "osm_id": [1, 2],
        "country": ["malta", "malta"],
        "wikidata_qid": ["Q1", "Q2"],
        "article_title": ["Foo", "Bar"],
        "article_body_text": ["a" * 100, "b" * 100],
        "geometry_wkt": ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
                         "POLYGON((2 2, 3 2, 3 3, 2 3, 2 2))"],
    }).write_parquet(plan.match_parquet)
    plan.match_jsonl.write_text('{"osm_id":1}\n')  # 1 line but parquet has 2 rows

    report = validate_country_outputs(plan)
    assert not report.ok
    assert any("jsonl" in e.lower() for e in report.errors)


def test_validate_skips_when_zero_matches(tmp_path: Path) -> None:
    """A country with all non-en sitelinks gets 0 matches — that's a valid skip."""
    plan = plan_country_run(country="italy", data_root=tmp_path, samples_root=tmp_path)
    plan.match_parquet.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "osm_id": pl.Series([], dtype=pl.Int64),
        "country": pl.Series([], dtype=pl.String),
        "wikidata_qid": pl.Series([], dtype=pl.String),
        "article_title": pl.Series([], dtype=pl.String),
        "article_body_text": pl.Series([], dtype=pl.String),
        "geometry_wkt": pl.Series([], dtype=pl.String),
    }).write_parquet(plan.match_parquet)
    plan.match_jsonl.write_text("")  # empty jsonl

    report = validate_country_outputs(plan)
    assert report.ok  # still OK
    assert report.skipped
    assert report.n_rows == 0