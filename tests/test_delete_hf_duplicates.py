"""Tests for safe deletion of duplicate HF dataset files at the root.

The migration left stale `<slug>_wikidata.{parquet,jsonl,html,png}` files at
HF dataset root while the new canonical layout ships them at
``per_country/<slug>/<slug>_wikidata.{parquet,jsonl,html,png}``.

This module provides ``delete_hf_duplicates`` which:
- lists every root file
- for each, looks up its canonical counterpart
- compares content (sha256 for binaries, row-set equality for parquet)
- deletes only verified duplicates; keeps anything that has no destination
  or differs from its destination
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.layout.delete_hf_duplicates import (
    classify_hf_file,
    is_safe_to_delete_hf_root_file,
)


# --- pure unit tests (no HF API calls) ------------------------------------


def test_classify_hf_file_recognises_wikidata_parquet() -> None:
    assert classify_hf_file("poland_wikidata.parquet") == ("poland", "per_country/poland/poland.parquet")
    assert classify_hf_file("andorra_wikidata.jsonl") == ("andorra", "per_country/andorra/andorra_wikidata.jsonl")
    assert classify_hf_file("italy_wikidata_map.html") == ("italy", "per_country/italy/italy_wikidata_map.html")


def test_classify_hf_file_handles_polygons_map() -> None:
    assert classify_hf_file("andorra_polygons_map.html") == ("andorra", "per_country/andorra/andorra_polygons_map.html")
    assert classify_hf_file("andorra_polygons_map.png") == ("andorra", "per_country/andorra/andorra_polygons_map.png")


def test_classify_hf_file_handles_union_aggregate() -> None:
    assert classify_hf_file("all_wikidata.parquet") == ("all", "combined/all_europe.parquet")
    assert classify_hf_file("all_wikidata_map.png") == ("all", "preview/map_preview.png")
    assert classify_hf_file("all_wikidata_map.html") == ("all", "preview/map_preview.html")


def test_classify_hf_file_handles_andorra_orphan() -> None:
    """The ``andorra.parquet`` orphan sits at root with no ``_wikidata`` suffix."""
    assert classify_hf_file("andorra.parquet") == ("andorra", "per_country/andorra/andorra.parquet")


def test_classify_hf_file_handles_unrecognised() -> None:
    """Files we have no canonical mapping for must return None."""
    assert classify_hf_file("README.md") is None
    assert classify_hf_file("manifest") is None
    assert classify_hf_file("metadata") is None
    assert classify_hf_file(".gitattributes") is None


# --- byte-equivalence safety check (uses a tmpdir) -----------------------


def test_is_safe_to_delete_hf_root_file_byte_identical(tmp_path: Path) -> None:
    root = tmp_path / "poland_wikidata.parquet"
    target = tmp_path / "per_country" / "poland" / "poland.parquet"
    target.parent.mkdir(parents=True)
    root.write_bytes(b"<same>")
    target.write_bytes(b"<same>")
    assert is_safe_to_delete_hf_root_file(root, target) is True


def test_is_safe_to_delete_hf_root_file_different(tmp_path: Path) -> None:
    root = tmp_path / "poland_wikidata.parquet"
    target = tmp_path / "per_country" / "poland" / "poland.parquet"
    target.parent.mkdir(parents=True)
    root.write_bytes(b"<A>")
    target.write_bytes(b"<B>")
    assert is_safe_to_delete_hf_root_file(root, target) is False


def test_is_safe_to_delete_hf_root_file_parquet_row_equivalence(tmp_path: Path) -> None:
    """For parquet files, also accept deletion if the row-set is identical
    (different schemas OK)."""
    a = tmp_path / "all_wikidata.parquet"
    b = tmp_path / "combined" / "all_europe.parquet"
    b.parent.mkdir()
    legacy = pl.DataFrame({"osm_id": [1, 2], "country": ["p", "p"], "extra": ["x", "y"]})
    new = pl.DataFrame({"osm_id": [1, 2], "country": ["p", "p"]})
    legacy.write_parquet(a)
    new.write_parquet(b)
    assert is_safe_to_delete_hf_root_file(a, b) is True


def test_is_safe_to_delete_hf_root_file_parquet_different_rows(tmp_path: Path) -> None:
    a = tmp_path / "all_wikidata.parquet"
    b = tmp_path / "combined" / "all_europe.parquet"
    b.parent.mkdir()
    legacy = pl.DataFrame({"osm_id": [1, 2], "country": ["p", "p"]})
    new = pl.DataFrame({"osm_id": [1, 2, 3], "country": ["p", "p", "x"]})
    legacy.write_parquet(a)
    new.write_parquet(b)
    assert is_safe_to_delete_hf_root_file(a, b) is False


def test_is_safe_to_delete_hf_root_file_missing_target(tmp_path: Path) -> None:
    """If the canonical copy doesn't exist (locally or on HF), do not delete."""
    root = tmp_path / "poland_wikidata.parquet"
    target = tmp_path / "per_country" / "poland" / "poland.parquet"
    root.write_bytes(b"<data>")
    # target file doesn't exist
    assert is_safe_to_delete_hf_root_file(root, target) is False
