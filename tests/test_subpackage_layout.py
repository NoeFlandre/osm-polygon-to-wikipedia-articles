"""Tests for the subpackage layout of ``osm_polygon_to_wikipedia_articles.wikipedia``.

The ``wikipedia`` package grew to ~20 flat modules. To keep it navigable
the modules are now grouped into five subpackages, each with a single
responsibility:

    fetch/         HTTP layer (Wikidata, Wikipedia REST, batched API)
    pipeline/      Pure logic + match orchestrator
    visualization/ folium maps + PNG renderer
    layout/        Canonical 4-subfolder dataset layout
    orchestration/ Per-country end-to-end driver

This file locks in the structure: every public symbol is reachable from
its expected subpackage, and the top-level package still re-exports the
back-compat names so the existing scripts and tests don't need to change.
"""
from __future__ import annotations

import importlib

import pytest


# --- 1. Each subpackage exists and is importable ------------------------

SUBPACKAGES = [
    "osm_polygon_to_wikipedia_articles.wikipedia.fetch",
    "osm_polygon_to_wikipedia_articles.wikipedia.pipeline",
    "osm_polygon_to_wikipedia_articles.wikipedia.visualization",
    "osm_polygon_to_wikipedia_articles.wikipedia.layout",
    "osm_polygon_to_wikipedia_articles.wikipedia.orchestration",
]


@pytest.mark.parametrize("modname", SUBPACKAGES)
def test_subpackage_is_importable(modname: str) -> None:
    mod = importlib.import_module(modname)
    # Each subpackage must have a top-level docstring describing its job
    assert mod.__doc__, f"{modname} has no docstring"
    assert len(mod.__doc__.strip()) > 30, f"{modname} docstring is too thin"


# --- 2. Public symbols are reachable from their subpackage ---------------

PUBLIC_SYMBOLS_BY_SUBPACKAGE = {
    "osm_polygon_to_wikipedia_articles.wikipedia.fetch": [
        "get_json_with_retry",
        "fetch_wikidata_sitelinks",
        "fetch_sitelinks_batched",
        "fetch_summary",
        "fetch_extract",
    ],
    "osm_polygon_to_wikipedia_articles.wikipedia.pipeline": [
        "MatchResult",
        "ArticleSummary",
        "WikidataArticle",
        "extract_wikidata_qid",
        "filter_polygons_with_wikidata",
        "resolve_wikidata_to_article",
        "match_polygons",
        "union_jsonls",
        "is_svg_url",
        "add_thumbnail_columns",
    ],
    "osm_polygon_to_wikipedia_articles.wikipedia.visualization": [
        "build_map",
        "build_polygon_map",
        "render_map_png",
    ],
    "osm_polygon_to_wikipedia_articles.wikipedia.layout": [
        "RootPaths",
        "CountryPaths",
        "CombinedPaths",
        "SamplePaths",
        "PreviewPaths",
        "build_all_europe",
        "build_sample_map",
        "write_manifest_json",
        "build_metadata_json",
        "migrate_to_full_layout",
        "safe_delete_audited",
        "classify_hf_file",
        "is_safe_to_delete_hf_root_file",
    ],
    "osm_polygon_to_wikipedia_articles.wikipedia.orchestration": [
        "CountryPlan",
        "ValidationReport",
        "discover_countries_with_wikidata",
        "plan_country_run",
        "validate_country_outputs",
        "process_all",
    ],
}


@pytest.mark.parametrize(
    "modname,symbols",
    list(PUBLIC_SYMBOLS_BY_SUBPACKAGE.items()),
)
def test_public_symbols_are_reexported(modname: str, symbols: list[str]) -> None:
    mod = importlib.import_module(modname)
    missing = [s for s in symbols if not hasattr(mod, s)]
    assert not missing, f"{modname} is missing public symbols: {missing}"


# --- 3. Backward-compat: top-level re-exports still work ----------------

# These are the names scripts and tests historically imported from the
# top-level ``wikipedia`` package. They MUST remain reachable so the
# ``scripts/*.py`` files don't need to be edited in lockstep with the
# subfolder refactor.
LEGACY_TOP_LEVEL_NAMES = [
    # fetch
    "fetch_wikidata_sitelinks",
    "fetch_sitelinks_batched",
    "fetch_summary",
    "fetch_extract",
    "get_json_with_retry",
    # pipeline
    "match_polygons",
    "MatchResult",
    "ArticleSummary",
    "WikidataArticle",
    "extract_wikidata_qid",
    "filter_polygons_with_wikidata",
    "resolve_wikidata_to_article",
    "union_jsonls",
    "is_svg_url",
    "add_thumbnail_columns",
    # visualization
    "build_map",
    "build_polygon_map",
    "render_map_png",
    # layout
    "RootPaths",
    "CountryPaths",
    "CombinedPaths",
    "SamplePaths",
    "PreviewPaths",
    "build_all_europe",
    "build_sample_map",
    "write_manifest_json",
    "build_metadata_json",
    "migrate_to_full_layout",
    "safe_delete_audited",
    "classify_hf_file",
    "is_safe_to_delete_hf_root_file",
    # orchestration
    "CountryPlan",
    "ValidationReport",
    "process_all",
]


def test_legacy_top_level_names_still_importable() -> None:
    import osm_polygon_to_wikipedia_articles.wikipedia as wp
    missing = [n for n in LEGACY_TOP_LEVEL_NAMES if not hasattr(wp, n)]
    assert not missing, f"wikipedia package lost these public names: {missing}"


# --- 4. Subpackages have no cyclic import errors ------------------------

def test_no_cyclic_import_errors() -> None:
    """Importing every subpackage in order should not raise."""
    for modname in SUBPACKAGES:
        importlib.import_module(modname)
