"""Wikipedia article matching + dataset publication layer.

This package is organised into five subpackages, each with a single
responsibility:

- :mod:`.fetch`         — HTTP layer (Wikidata, Wikipedia REST, batched API)
- :mod:`.pipeline`      — pure logic + match orchestrator
- :mod:`.visualization` — folium maps + PNG renderer
- :mod:`.layout`        — canonical 4-subfolder dataset layout
- :mod:`.orchestration` — per-country end-to-end driver

For back-compat, the top-level package re-exports every public symbol
that scripts and tests historically imported directly from
``wikipedia``. New code is encouraged to import from the subpackage::

    from osm_polygon_to_wikipedia_articles.wikipedia.fetch import (
        fetch_wikidata_sitelinks,
    )
    from osm_polygon_to_wikipedia_articles.wikipedia.pipeline import (
        match_polygons,
    )

…but the legacy ``from osm_polygon_to_wikipedia_articles.wikipedia.match
import match_polygons`` continues to work.
"""
from __future__ import annotations

# --- subpackage re-exports -----------------------------------------------
from . import fetch, layout, orchestration, pipeline, visualization

# --- back-compat re-exports (do not remove without updating scripts) ----
# fetch
from .fetch import (  # noqa: F401
    fetch_extract,
    fetch_sitelinks_batched,
    fetch_summary,
    fetch_wikidata_sitelinks,
    fetch_wikipedia_extract,
    fetch_wikipedia_summary,
    get_json_with_retry,
)
# pipeline
from .pipeline import (  # noqa: F401
    ArticleSummary,
    MatchResult,
    WikidataArticle,
    add_thumbnail_columns,
    discover_per_country_jsonls,
    extract_wikidata_qid,
    filter_polygons_with_wikidata,
    is_svg_url,
    match_polygons,
    resolve_wikidata_to_article,
    union_jsonls,
)
# visualization
from .visualization import (  # noqa: F401
    build_map,
    build_polygon_map,
    parse_geometry_wkt,
    render_map_png,
)
# layout
from .layout import (  # noqa: F401
    CombinedPaths,
    CountryPaths,
    PreviewPaths,
    RootPaths,
    SamplePaths,
    build_all_europe,
    build_metadata_json,
    build_sample_map,
    classify_hf_file,
    combined_paths_for,
    country_paths_for,
    is_safe_to_delete_hf_root_file,
    migrate_to_full_layout,
    preview_paths_for,
    root_paths_for,
    sample_paths_for,
    safe_delete_audited,
    survey_remotely_deleted_duplicates,
    write_manifest_json,
    write_top_readme,
)
# orchestration
from .orchestration import (  # noqa: F401
    CountryPlan,
    ValidationReport,
    discover_countries_with_wikidata,
    plan_country_run,
    process_all,
    process_one_country,
    validate_country_outputs,
)

__all__ = [
    # subpackages
    "fetch",
    "layout",
    "orchestration",
    "pipeline",
    "visualization",
    # fetch
    "fetch_extract",
    "fetch_sitelinks_batched",
    "fetch_summary",
    "fetch_wikidata_sitelinks",
    "fetch_wikipedia_extract",
    "fetch_wikipedia_summary",
    "get_json_with_retry",
    # pipeline
    "ArticleSummary",
    "MatchResult",
    "WikidataArticle",
    "add_thumbnail_columns",
    "discover_per_country_jsonls",
    "extract_wikidata_qid",
    "filter_polygons_with_wikidata",
    "is_svg_url",
    "match_polygons",
    "resolve_wikidata_to_article",
    "union_jsonls",
    # visualization
    "build_map",
    "build_polygon_map",
    "parse_geometry_wkt",
    "render_map_png",
    # layout
    "CombinedPaths",
    "CountryPaths",
    "PreviewPaths",
    "RootPaths",
    "SamplePaths",
    "build_all_europe",
    "build_metadata_json",
    "build_sample_map",
    "classify_hf_file",
    "combined_paths_for",
    "country_paths_for",
    "is_safe_to_delete_hf_root_file",
    "migrate_to_full_layout",
    "preview_paths_for",
    "root_paths_for",
    "sample_paths_for",
    "safe_delete_audited",
    "survey_remotely_deleted_duplicates",
    "write_manifest_json",
    "write_top_readme",
    # orchestration
    "CountryPlan",
    "ValidationReport",
    "discover_countries_with_wikidata",
    "plan_country_run",
    "process_all",
    "process_one_country",
    "validate_country_outputs",
]
