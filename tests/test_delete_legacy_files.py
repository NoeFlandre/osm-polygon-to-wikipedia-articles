"""Tests for the safe-deletion helper used during the layout migration.

The deletion must be *opt-in* per file path — we never delete anything that
isn't on the SAFE list computed by the audit.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.delete_legacy import (
    safe_delete,
    safe_delete_audited,
)


# --- safe_delete: takes a list of paths ----------------------------------


def _touch(p: Path, content: bytes = b"x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)


def test_safe_delete_removes_listed_files(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    c = tmp_path / "c.txt"
    a.write_text("a"); b.write_text("b"); c.write_text("c")
    removed = safe_delete([a, b])
    assert sorted(p.name for p in removed) == ["a.txt", "b.txt"]
    assert not a.exists() and not b.exists()
    assert c.exists()  # untouched


def test_safe_delete_skips_missing(tmp_path: Path) -> None:
    a = tmp_path / "present.txt"
    a.write_text("x")
    missing = tmp_path / "gone.txt"
    removed = safe_delete([a, missing])
    assert removed == [a]
    assert not a.exists()


def test_safe_delete_refuses_nested_targets(tmp_path: Path) -> None:
    """A nested file inside an already-deleted dir must not blow up."""
    d = tmp_path / "d"
    d.mkdir()
    (d / "f.txt").write_text("y")
    assert not isinstance(safe_delete([d / "f.txt"]), type(None))


# --- safe_delete_audited: discover-then-delete by audit rules ----------


def test_safe_delete_audited_drops_byte_identical_html_maps(tmp_path: Path) -> None:
    """Top-level ``<slug>_wikidata_map.html`` whose per-country copy has the
    same sha256 should be deleted."""
    samples = tmp_path
    pc = samples / "per_country" / "poland"
    pc.mkdir(parents=True)
    content = b"<html>poland</html>"
    (samples / "poland_wikidata_map.html").write_bytes(content)
    (pc / "poland_wikidata_map.html").write_bytes(content)
    # Also a non-related file that must NOT be deleted
    keep = samples / "manifest"
    keep.write_text("keep me")

    removed = safe_delete_audited(samples, dry_run=False)

    assert any(p.name == "poland_wikidata_map.html" and p.parent == samples for p in removed)
    assert not (samples / "poland_wikidata_map.html").exists()
    assert keep.exists()


def test_safe_delete_audited_dry_run_makes_no_changes(tmp_path: Path) -> None:
    samples = tmp_path
    pc = samples / "per_country" / "italy"
    pc.mkdir(parents=True)
    content = b"<html>italy</html>"
    (samples / "italy_wikidata_map.html").write_bytes(content)
    (pc / "italy_wikidata_map.html").write_bytes(content)

    removed = safe_delete_audited(samples, dry_run=True)
    assert removed, "dry-run should still report matches"
    assert (samples / "italy_wikidata_map.html").exists()


def test_safe_delete_audited_keeps_non_duplicates(tmp_path: Path) -> None:
    """If a legacy file has no destination yet, do not delete it."""
    samples = tmp_path
    (samples / "andorra_wikidata_map.html").write_bytes(b"<html>andorra</html>")
    # No per_country/andorra folder exists → nothing to compare against

    removed = safe_delete_audited(samples, dry_run=False)
    assert removed == []
    # File is still there because no canonical destination exists.
    assert (samples / "andorra_wikidata_map.html").exists()


def test_safe_delete_audited_handles_polygons_map(tmp_path: Path) -> None:
    """Legacy ``<slug>_polygons_map.{html,png}`` should be deleted when
    per_country/<slug>/<slug>_polygons_map.{html,png} matches."""
    samples = tmp_path
    pc = samples / "per_country" / "andorra"
    pc.mkdir(parents=True)
    content = b"<html>polygons</html>"
    (samples / "andorra_polygons_map.html").write_bytes(content)
    (pc / "andorra_polygons_map.html").write_bytes(content)

    removed = safe_delete_audited(samples, dry_run=False)
    assert any(p.name == "andorra_polygons_map.html" and p.parent == samples for p in removed)
    assert not (samples / "andorra_polygons_map.html").exists()


def test_safe_delete_audited_handles_union_aggregate_row_equiv(tmp_path: Path) -> None:
    """all_wikidata.parquet (legacy union) has a different byte-for-byte schema
    than combined/all_europe.parquet (rebuilt), but the row set is the same.
    Audit should still treat it as safe to delete."""
    import polars as pl
    samples = tmp_path
    (samples / "combined").mkdir()
    (samples / "preview").mkdir()
    # Two parquets with different schemas but identical (osm_id, country)
    legacy = pl.DataFrame({
        "osm_id": [1, 2, 3], "country": ["poland", "poland", "italy"],
        "extra_field": ["x", "y", "z"],  # different schema
    })
    new = pl.DataFrame({
        "osm_id": [1, 2, 3], "country": ["poland", "poland", "italy"],
    })
    legacy.write_parquet(samples / "all_wikidata.parquet")
    new.write_parquet(samples / "combined" / "all_europe.parquet")

    removed = safe_delete_audited(samples, dry_run=False)
    assert any(p.name == "all_wikidata.parquet" and p.parent == samples for p in removed)
    assert not (samples / "all_wikidata.parquet").exists()


def test_safe_delete_audited_idempotent(tmp_path: Path) -> None:
    """Running twice: second run removes nothing."""
    samples = tmp_path
    pc = samples / "per_country" / "germany"
    pc.mkdir(parents=True)
    content = b"<html>de</html>"
    (samples / "germany_wikidata_map.html").write_bytes(content)
    (pc / "germany_wikidata_map.html").write_bytes(content)

    first = safe_delete_audited(samples, dry_run=False)
    second = safe_delete_audited(samples, dry_run=False)
    assert len(first) >= 1
    assert second == []
