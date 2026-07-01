"""Tests for the target four-subfolder dataset layout.

Target structure (replacing the flat data/samples/):

    dataset/
    ├── README.md
    ├── manifest                        # NEW
    ├── metadata                        # NEW
    ├── per_country/                    # 46 country subfolders
    │   ├── README.md
    │   ├── <country>/
    │   │   ├── README.md
    │   │   └── <country>.parquet
    │   └── ...
    ├── combined/                       # 2 files
    │   ├── README.md
    │   └── all_europe.parquet          # full combined aggregate
    ├── sample/                         # 2 files
    │   ├── README.md
    │   └── sample_map.jsonl            # ~4200 polygons
    └── preview/                        # 2 files
        ├── README.md
        └── map_preview.png
"""
from __future__ import annotations

from pathlib import Path

import pytest

from osm_polygon_to_wikipedia_articles.wikipedia.full_layout import (
    COMBINED_DIR,
    PER_COUNTRY_DIR,
    PREVIEW_DIR,
    SAMPLE_DIR,
    CombinedPaths,
    CountryPaths,
    PreviewPaths,
    RootPaths,
    SamplePaths,
    build_all_europe,
    build_metadata_json,
    build_sample_map,
    combined_paths_for,
    country_paths_for,
    preview_paths_for,
    root_paths_for,
    sample_paths_for,
    write_manifest_json,
    write_top_readme,
)


# --- path tests ----------------------------------------------------------


def test_root_paths(tmp_path: Path) -> None:
    p = root_paths_for(tmp_path)
    assert isinstance(p, RootPaths)
    assert p.readme == tmp_path / "README.md"
    assert p.manifest == tmp_path / "manifest"
    assert p.metadata == tmp_path / "metadata"


def test_per_country_paths(tmp_path: Path) -> None:
    p = country_paths_for(tmp_path, "poland")
    assert isinstance(p, CountryPaths)
    assert p.folder == tmp_path / PER_COUNTRY_DIR / "poland"
    assert p.parquet == p.folder / "poland.parquet"
    assert p.readme == p.folder / "README.md"


def test_combined_paths(tmp_path: Path) -> None:
    p = combined_paths_for(tmp_path)
    assert p.parquet == tmp_path / COMBINED_DIR / "all_europe.parquet"
    assert p.readme == tmp_path / COMBINED_DIR / "README.md"


def test_sample_paths(tmp_path: Path) -> None:
    p = sample_paths_for(tmp_path)
    assert p.jsonl == tmp_path / SAMPLE_DIR / "sample_map.jsonl"
    assert p.readme == tmp_path / SAMPLE_DIR / "README.md"


def test_preview_paths(tmp_path: Path) -> None:
    p = preview_paths_for(tmp_path)
    assert p.png == tmp_path / PREVIEW_DIR / "map_preview.png"
    assert p.readme == tmp_path / PREVIEW_DIR / "README.md"


# --- manifest + metadata -------------------------------------------------


def test_write_manifest_json(tmp_path: Path) -> None:
    write_manifest_json(
        tmp_path,
        countries=["italy", "poland"],
        combined_rows=31462,
        combined_words=12688390,
        sample_rows=4204,
        svg_count=885,
    )
    manifest = tmp_path / "manifest"
    assert manifest.exists()
    import json as _j
    payload = _j.loads(manifest.read_text())
    assert sorted(payload["countries"]) == ["italy", "poland"]
    assert payload["combined_rows"] == 31462
    assert payload["sample_rows"] == 4204


def test_build_metadata_json() -> None:
    text = build_metadata_json(
        repo_url="https://huggingface.co/datasets/NoeFlandre/osm-polygon-to-wikipedia-articles",
        generated_at="2026-07-01T10:00:00Z",
        columns=["osm_id", "country", "wikidata_qid", "article_title", "thumbnail_is_svg"],
    )
    import json as _j
    p = _j.loads(text)
    assert p["repo_url"].startswith("https://")
    assert "thumbnail_is_svg" in p["columns"]


# --- builders ------------------------------------------------------------


def test_build_all_europe_concatenates_country_parquets(tmp_path: Path) -> None:
    """``build_all_europe`` produces the single ``all_europe.parquet`` from per-country parquets."""
    import polars as pl

    pc = tmp_path / PER_COUNTRY_DIR
    for slug, n in [("poland", 2), ("italy", 1)]:
        d = pc / slug
        d.mkdir(parents=True)
        pl.DataFrame({
            "osm_id": list(range(n)),
            "country": [slug] * n,
            "wikidata_qid": [f"Q{i}" for i in range(n)],
        }).write_parquet(d / f"{slug}.parquet")

    out = build_all_europe(tmp_path)
    assert out == tmp_path / COMBINED_DIR / "all_europe.parquet"
    df = pl.read_parquet(out)
    assert df.height == 3
    assert set(df["country"].unique()) == {"poland", "italy"}


def test_build_sample_map_picks_n_rows(tmp_path: Path) -> None:
    """``build_sample_map`` writes a JSONL of N rows from the combined."""
    import polars as pl

    pc = tmp_path / PER_COUNTRY_DIR
    d = pc / "poland"
    d.mkdir(parents=True)
    pl.DataFrame({
        "osm_id": list(range(100)),
        "country": ["poland"] * 100,
        "wikidata_qid": [f"Q{i}" for i in range(100)],
        "centroid_lon": [20.0] * 100,
        "centroid_lat": [52.0] * 100,
    }).write_parquet(d / "poland.parquet")

    out = build_sample_map(tmp_path, target_n=10, seed=42)
    assert out.exists()
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 10
    # Each line is JSON with osm_id
    import json as _j
    recs = [_j.loads(l) for l in lines]
    assert all("osm_id" in r for r in recs)


# --- top readme ----------------------------------------------------------


def test_write_top_readme(tmp_path: Path) -> None:
    p = write_top_readme(tmp_path, countries=46, total_rows=31462, total_words=12688390)
    assert p == tmp_path / "README.md"
    text = p.read_text()
    assert "per_country/" in text
    assert "combined/" in text
    assert "sample/" in text
    assert "preview/" in text


# --- constants -----------------------------------------------------------


def test_constants() -> None:
    for name, expected in [
        ("PER_COUNTRY_DIR", "per_country"),
        ("COMBINED_DIR", "combined"),
        ("SAMPLE_DIR", "sample"),
        ("PREVIEW_DIR", "preview"),
    ]:
        import osm_polygon_to_wikipedia_articles.wikipedia.full_layout as m
        assert getattr(m, name) == expected
