"""No double-listing: every name in each ``__init__.py`` appears in
exactly one place (the ``from .X import *`` line + the source module's
own ``__all__``). The goal of this test is to prevent the regression
of re-introducing a hand-maintained symbol list in addition to the
``__all__`` it duplicates.

Why this matters
----------------
The previous ``__init__.py`` files manually listed every public name
twice: once in the ``from .X import (...)`` block and once in
``__all__``. Total duplication across the package was 440 LOC. The
fix is to use ``from .X import *`` and let Python's ``__all__``
propagation do the work.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest


PKG = Path("src/osm_polygon_to_wikipedia_articles/wikipedia")
TOP_LEVEL_INIT = PKG / "__init__.py"
SUBPKG_INITS = sorted((PKG / d / "__init__.py") for d in
                      ("fetch", "layout", "orchestration", "pipeline", "visualization"))


# ---------------------------------------------------------------------------
# Top-level __init__ LOC cap
# ---------------------------------------------------------------------------

def test_top_level_init_lte_60_lines() -> None:
    """The top-level ``wikipedia/__init__.py`` should be terse.

    Old size was 158 LOC. The 60-line cap forces the file to rely on
    ``from .subpkg import *`` rather than enumerating symbols by hand.
    """
    lines = sum(1 for _ in TOP_LEVEL_INIT.read_text().splitlines())
    assert lines <= 60, f"{TOP_LEVEL_INIT} is {lines} lines (cap=60)"


@pytest.mark.parametrize("init_path", SUBPKG_INITS,
                         ids=lambda p: p.parent.name)
def test_subpkg_init_lte_70_lines(init_path: Path) -> None:
    """Each subpackage ``__init__.py`` should also be terse.

    Old sizes: fetch=50, layout=96, orchestration=43, pipeline=62,
    visualization=31. The 70-line cap fits all of them; using
    ``from .module import *`` instead of a hand-rolled ``__all__``
    trims the body further.
    """
    lines = sum(1 for _ in init_path.read_text().splitlines())
    assert lines <= 70, f"{init_path} is {lines} lines (cap=70)"


# ---------------------------------------------------------------------------
# The "double-listing" detection: no name should appear both in an
# explicit ``from .X import (...)`` and in a separate ``__all__`` list.
# ---------------------------------------------------------------------------

_DOUBLE_LISTING = re.compile(
    # match `from .foo import (a, b, c,)` or `from .foo import a, b, c`
    r"^from\s+\.[\w.]+\s+import\s+\(?\s*([^\n\)]+?)\s*[,)]?$",
    re.MULTILINE,
)
_ALL_BLOCK = re.compile(r"^__all__\s*=\s*\[(.*?)\]", re.MULTILINE | re.DOTALL)


@pytest.mark.parametrize("init_path", SUBPKG_INITS + [TOP_LEVEL_INIT],
                         ids=lambda p: p.parent.name or "top")
def test_init_has_no_double_listing(init_path: Path) -> None:
    """A name must not be both explicitly imported and listed in
    ``__all__``.  The whole point of this refactor is to remove the
    duplicate bookkeeping: ``__all__`` is the single source of truth.
    """
    text = init_path.read_text()

    explicit_names: set[str] = set()
    for m in _DOUBLE_LISTING.finditer(text):
        for name in m.group(1).split(","):
            name = name.strip()
            if name and not name.startswith("#"):
                explicit_names.add(name.split(" as ")[0])

    m_all = _ALL_BLOCK.search(text)
    if m_all is None:
        return  # no __all__ block at all
    all_names = {n.strip().strip('"').strip("'")
                 for n in m_all.group(1).split(",") if n.strip()}

    overlap = explicit_names & all_names
    assert not overlap, (
        f"{init_path}: {sorted(overlap)} appear both in `from .X import (...)` "
        "and `__all__` — pick one (the new convention is `__all__` only)."
    )


# ---------------------------------------------------------------------------
# Public API is preserved (regression guard)
# ---------------------------------------------------------------------------

def test_top_level_still_exposes_all_back_compat_symbols() -> None:
    """Every name that the back-compat surface used to expose must
    still be importable from the top-level package.

    This is the safety net: even with the new ``import *`` pattern,
    ``from osm_polygon_to_wikipedia_articles.wikipedia import match_polygons``
    must keep working.
    """
    import osm_polygon_to_wikipedia_articles.wikipedia as wp  # noqa: E402

    expected = {
        # fetch
        "fetch_extract", "fetch_sitelinks_batched", "fetch_summary",
        "fetch_wikidata_sitelinks", "fetch_wikipedia_extract",
        "fetch_wikipedia_summary", "get_json_with_retry",
        # pipeline
        "ArticleSummary", "MatchResult", "WikidataArticle",
        "add_thumbnail_columns", "discover_per_country_jsonls",
        "extract_wikidata_qid", "filter_polygons_with_wikidata",
        "is_svg_url", "match_polygons", "resolve_wikidata_to_article",
        "union_jsonls",
        # visualization
        "build_map", "build_polygon_map", "parse_geometry_wkt",
        "render_map_png",
        # layout
        "CombinedPaths", "CountryPaths", "PreviewPaths", "RootPaths",
        "SamplePaths", "build_all_europe", "build_metadata_json",
        "build_sample_map", "classify_hf_file", "combined_paths_for",
        "country_paths_for", "is_safe_to_delete_hf_root_file",
        "migrate_to_full_layout", "preview_paths_for",
        "root_paths_for", "sample_paths_for", "safe_delete_audited",
        "survey_remotely_deleted_duplicates", "write_manifest_json",
        "write_top_readme",
        # orchestration
        "CountryPlan", "ValidationReport",
        "discover_countries_with_wikidata", "plan_country_run",
        "process_all", "process_one_country", "validate_country_outputs",
    }
    missing = expected - set(wp.__all__)
    assert not missing, f"missing from top-level __all__: {sorted(missing)}"
    for name in expected:
        assert hasattr(wp, name), f"top-level has no attribute {name!r}"


def test_subpackage_wildcard_imports_use_dunder_all() -> None:
    """Each subpackage's ``from .module import *`` actually imports
    the module's ``__all__`` names.

    This guards against the case where the new pattern silently drops
    a name because the source module's ``__all__`` is empty.
    """
    from osm_polygon_to_wikipedia_articles.wikipedia import fetch  # noqa: E402
    from osm_polygon_to_wikipedia_articles.wikipedia import layout  # noqa: E402
    from osm_polygon_to_wikipedia_articles.wikipedia import pipeline  # noqa: E402
    from osm_polygon_to_wikipedia_articles.wikipedia import (  # noqa: E402
        orchestration, visualization,
    )

    for sub, must_have in [
        (fetch, {"fetch_summary", "fetch_sitelinks_batched",
                 "fetch_wikidata_sitelinks", "get_json_with_retry"}),
        (layout, {"build_all_europe", "build_sample_map",
                  "migrate_to_full_layout", "safe_delete_audited",
                  "classify_hf_file"}),
        (pipeline, {"match_polygons", "union_jsonls",
                    "is_svg_url", "extract_wikidata_qid"}),
        (orchestration, {"process_one_country", "process_all",
                         "plan_country_run"}),
        (visualization, {"build_map", "render_map_png"}),
    ]:
        missing = must_have - set(getattr(sub, "__all__", ()))
        assert not missing, (
            f"{sub.__name__} missing from __all__: {sorted(missing)}"
        )
