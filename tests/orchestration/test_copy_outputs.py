"""Tests for the ``copy_country_outputs_to_samples`` helper.

The old ``process_all`` had an inline 4-line copy block::

    for src, dst in [
        (plan.match_parquet, plan.samples_match_parquet),
        (plan.match_jsonl, plan.samples_match_jsonl),
        (plan.match_map_html, plan.samples_match_map_html),
        (plan.match_map_png, plan.samples_match_png),
    ]:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

These tests lock in the extracted helper so callers don't re-inline
the loop and accidentally drop a file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.orchestration.process_countries import (
    copy_country_outputs_to_samples,
)


def _plan(samples_root: Path, data_root: Path, country: str):
    """Build the four (src, dst) pairs the helper should copy."""
    return {
        "match_parquet": (data_root / f"{country}_wikidata.parquet",
                          samples_root / f"{country}_wikidata.parquet"),
        "match_jsonl": (data_root / f"{country}_wikidata.jsonl",
                        samples_root / f"{country}_wikidata.jsonl"),
        "match_map_html": (data_root / f"{country}_wikidata_map.html",
                           samples_root / f"{country}_wikidata_map.html"),
        "match_map_png": (data_root / f"{country}_wikidata_map.png",
                          samples_root / f"{country}_wikidata_map.png"),
    }


def test_copies_all_four_files(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src_root.mkdir()
    pairs = _plan(dst_root, src_root, "italy")
    for src, _dst in pairs.values():
        src.write_text("data")
    plan = {k: {"src": v[0], "dst": v[1]} for k, v in pairs.items()}

    n = copy_country_outputs_to_samples(plan)
    assert n == 4
    for src, dst in pairs.values():
        assert dst.read_text() == "data"


def test_creates_parent_directories(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst" / "deeply" / "nested"
    src_root.mkdir()
    pairs = _plan(dst_root, src_root, "poland")
    for src, _dst in pairs.values():
        src.write_text("x")
    plan = {k: {"src": v[0], "dst": v[1]} for k, v in pairs.items()}

    copy_country_outputs_to_samples(plan)
    assert (dst_root / "poland_wikidata.parquet").exists()


def test_skips_missing_source_files(tmp_path: Path) -> None:
    """The helper should be robust to missing source files (the
    process_all caller runs subprocess scripts that may not have
    produced every artefact, e.g. when there were no matches).
    """
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src_root.mkdir()
    pairs = _plan(dst_root, src_root, "andorra")
    # Only create the parquet + jsonl, leave map files absent
    pairs["match_parquet"][0].write_text("data")
    pairs["match_jsonl"][0].write_text("data")
    plan = {k: {"src": v[0], "dst": v[1]} for k, v in pairs.items()}

    n = copy_country_outputs_to_samples(plan)
    assert n == 2  # only the two that exist
    assert (dst_root / "andorra_wikidata.parquet").exists()
    assert (dst_root / "andorra_wikidata.jsonl").exists()
    assert not (dst_root / "andorra_wikidata_map.html").exists()


def test_returns_zero_when_nothing_exists(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dst_root = tmp_path / "dst"
    src_root.mkdir()
    pairs = _plan(dst_root, src_root, "andorra")
    plan = {k: {"src": v[0], "dst": v[1]} for k, v in pairs.items()}

    n = copy_country_outputs_to_samples(plan)
    assert n == 0


def test_validation_report_has_one_skipped_field() -> None:
    """Regression: ``ValidationReport`` previously declared
    ``skipped`` twice in its body.  The Python dataclass would have
    raised on definition; assert the field exists exactly once.
    """
    from osm_polygon_to_wikipedia_articles.wikipedia.orchestration.process_countries import (
        ValidationReport,
    )
    fields = {f.name for f in ValidationReport.__dataclass_fields__.values()}
    # Count occurrences in source so we catch a double declaration
    import inspect
    src = inspect.getsource(ValidationReport)
    assert src.count("skipped:") == 1, (
        f"ValidationReport declares 'skipped:' {src.count('skipped:')} times; "
        "should be exactly 1."
    )
    assert "skipped" in fields
