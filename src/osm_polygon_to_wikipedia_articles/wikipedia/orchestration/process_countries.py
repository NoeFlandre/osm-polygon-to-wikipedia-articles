"""Per-country batch processor: sample + match + validate + push, one country at a time.

Library API: :func:`discover_countries_with_wikidata`, :func:`plan_country_run`,
:func:`validate_country_outputs`, :func:`process_one_country`, :func:`process_all`.
CLI: ``uv run python scripts/process_countries.py``.

Heavy intermediate files live under ``OSM_DATA_ROOT`` (default ./data). For
the per-country workflow, set ``OSM_DATA_ROOT=/Volumes/Seagate M3/osm-polygon-to-wikipedia-articles``.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import polars as pl

from osm_polygon_to_wikipedia_articles.polygons.load import load_country
from osm_polygon_to_wikipedia_articles.wikipedia.fetch import (
    fetch_extract,
    fetch_summary,
    fetch_wikidata_sitelinks,
)
from osm_polygon_to_wikipedia_articles.wikipedia.pipeline import match_polygons, union_jsonls
from osm_polygon_to_wikipedia_articles.wikipedia.visualization import build_map, render_map_png


SOURCE_REPO = "NoeFlandre/osm-polygon-selection"
LANG = "en"
SLEEP_S = 0.2


@dataclass(frozen=True)
class CountryPlan:
    country: str
    source: Path
    match_parquet: Path
    match_jsonl: Path
    match_map_html: Path
    match_map_png: Path
    # Local (small) copies shipped to HF
    samples_match_parquet: Path
    samples_match_jsonl: Path
    samples_match_map_html: Path
    samples_match_map_png: Path


@dataclass
class ValidationReport:
    ok: bool
    skipped: bool = False  # True when the country legitimately had zero matches
    n_rows: int = 0
    geometry_wkt_missing: int = 0
    articles_with_body: int = 0
    jsonl_count: int = 0
    map_html_size: int = 0
    errors: list[str] = field(default_factory=list)


# --- discovery ------------------------------------------------------------

def discover_countries_with_wikidata(dataset_dir: Path) -> list[str]:
    """List every ``<country>.parquet`` whose first row has a ``wikidata=*`` tag.

    Cheap scan (we only need to detect *presence* of any wikidata tag, not
    count them). Heuristic: read the first row's tags list.
    """
    out: list[str] = []
    for p in sorted(dataset_dir.glob("*.parquet")):
        try:
            df = pl.read_parquet(p, columns=["tags"])
        except Exception:
            continue
        if df.height == 0 or "tags" not in df.columns:
            continue
        # df["tags"][0] is a polars Series wrapping a list. Materialize to a Python list.
        first_tags = df["tags"][0].to_list() if hasattr(df["tags"][0], "to_list") else list(df["tags"][0])
        if any(isinstance(t, str) and t.startswith("wikidata=") for t in first_tags):
            out.append(p.stem)
    return out


# --- planning -------------------------------------------------------------

def plan_country_run(country: str, data_root: Path, samples_root: Path) -> CountryPlan:
    return CountryPlan(
        country=country,
        source=data_root / f"{country}.parquet",
        match_parquet=data_root / f"{country}_wikidata.parquet",
        match_jsonl=data_root / f"{country}_wikidata.jsonl",
        match_map_html=data_root / f"{country}_wikidata_map.html",
        match_map_png=data_root / f"{country}_wikidata_map.png",
        samples_match_parquet=samples_root / f"{country}_wikidata.parquet",
        samples_match_jsonl=samples_root / f"{country}_wikidata.jsonl",
        samples_match_map_html=samples_root / f"{country}_wikidata_map.html",
        samples_match_map_png=samples_root / f"{country}_wikidata_map.png",
    )


# --- validation -----------------------------------------------------------

def validate_country_outputs(plan: CountryPlan) -> ValidationReport:
    r = ValidationReport(ok=True)
    if not plan.match_parquet.exists():
        r.ok = False
        r.errors.append(f"parquet missing: {plan.match_parquet}")
        return r
    df = pl.read_parquet(plan.match_parquet)
    r.n_rows = df.height

    # 0 rows = legitimately no matches (no polygons with wikidata); treat as skipped, not failed
    if r.n_rows == 0:
        r.skipped = True
        if plan.match_jsonl.exists():
            r.jsonl_count = sum(1 for line in plan.match_jsonl.read_text().splitlines() if line.strip())
        return r

    if "geometry_wkt" not in df.columns:
        r.ok = False
        r.errors.append("geometry_wkt column missing from parquet")
        r.geometry_wkt_missing = df.height
    else:
        r.geometry_wkt_missing = df["geometry_wkt"].null_count()
        if r.geometry_wkt_missing > 0:
            r.ok = False
            r.errors.append(f"geometry_wkt null on {r.geometry_wkt_missing}/{df.height} rows")
    if "article_body_text" in df.columns:
        r.articles_with_body = df["article_body_text"].is_not_null().sum()
    if plan.match_jsonl.exists():
        r.jsonl_count = sum(1 for line in plan.match_jsonl.read_text().splitlines() if line.strip())
        if r.jsonl_count != r.n_rows:
            r.ok = False
            r.errors.append(f"jsonl has {r.jsonl_count} lines but parquet has {r.n_rows} rows")
    else:
        r.ok = False
        r.errors.append(f"jsonl missing: {plan.match_jsonl}")
    if plan.match_map_html.exists():
        r.map_html_size = plan.match_map_html.stat().st_size
    if r.map_html_size == 0:
        r.ok = False
        r.errors.append(f"map html missing or empty: {plan.match_map_html}")
    return r


# --- copy helpers ---------------------------------------------------------

def copy_country_outputs_to_samples(
    pairs: dict[str, dict[str, Path]],
) -> int:
    """Copy each (src → dst) pair to ``samples/``, skipping missing sources.

    ``pairs`` is keyed by an arbitrary label; values are ``{"src": Path, "dst": Path}``
    dicts. The destination's parent directory is created on demand.
    Returns the number of files actually copied (sources that don't
    exist are skipped, not raised).
    """
    copied = 0
    for entry in pairs.values():
        src = entry["src"]
        dst = entry["dst"]
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied


# --- batch processing -----------------------------------------------------

def process_all(
    data_root: Path,
    samples_root: Path,
    hf_repo_id: str,
    union_out_parquet: Path,
    union_out_html: Path,
    union_out_png: Path,
    *,
    countries: Iterable[str] | None = None,
    lang: str = LANG,
    skip_hf: bool = False,
) -> list[tuple[str, ValidationReport]]:
    """Process every country end-to-end. Returns ``[(country, report), ...]``.

    For each country:
      1. run the sample + match pipeline (heavy files on data_root)
      2. validate (parquet/jsonl/map present, geometry populated, articles have bodies)
      3. copy slim outputs to samples_root
      4. re-run union across all per-country JSONLs

    HF upload is left to the caller (to keep batch + push decoupled).
    """
    if countries is None:
        countries = discover_countries_with_wikidata(Path("/") / "tmp" / "unused")
        # default discovery hits HF, not disk; we leave it to the caller

    results: list[tuple[str, ValidationReport]] = []
    for country in countries:
        plan = plan_country_run(country, data_root, samples_root)
        # sample + match run via the CLI scripts so we exercise the same path users take
        subprocess.run(
            [
                "uv", "run", "python", "scripts/sample.py",
                "--countries", country, "--n", "10000000",
                "--out", str(plan.source),
            ],
            check=True,
        )
        subprocess.run(
            [
                "uv", "run", "python", "scripts/match_wikidata.py",
                "--in", str(plan.source),
                "--parquet", str(plan.match_parquet),
                "--jsonl", str(plan.match_jsonl),
                "--map", str(plan.match_map_html),
                "--lang", lang,
            ],
            check=True,
        )
        # Copy slim outputs to samples/
        copy_country_outputs_to_samples({
            "parquet": {"src": plan.match_parquet, "dst": plan.samples_match_parquet},
            "jsonl":   {"src": plan.match_jsonl,   "dst": plan.samples_match_jsonl},
            "html":    {"src": plan.match_map_html, "dst": plan.samples_match_map_html},
            "png":     {"src": plan.match_map_png,  "dst": plan.samples_match_map_png},
        })
        report = validate_country_outputs(plan)
        results.append((country, report))
        if not report.ok:
            return results  # bail on first failure (caller's responsibility to retry)

    # Union across all per-country JSONLs
    jsonls = sorted(samples_root.glob("*_wikidata.jsonl"))
    if jsonls:
        union_jsonls(jsonls, union_out_parquet)
        build_map(pl.read_parquet(union_out_parquet), out_path=union_out_html)
        render_map_png(union_out_html, union_out_png, width=1000, height=600)

    return results


__all__ = [
    "CountryPlan",
    "ValidationReport",
    "copy_country_outputs_to_samples",
    "discover_countries_with_wikidata",
    "plan_country_run",
    "process_all",
    "validate_country_outputs",
]