"""Per-country batch processor: sample + match + validate + push, one country at a time.

Discovers every country in the source dataset that has at least one polygon
with a ``wikidata=*`` tag and processes them in alphabetical order, on the
external Seagate HDD (or wherever ``OSM_DATA_ROOT`` points).

Each country:
  1. sample -> heavy parquet on $OSM_DATA_ROOT
  2. match -> heavy parquet/jsonl/map.html/map.png on $OSM_DATA_ROOT
  3. validate (parquet/jsonl/map present, geometry populated, articles have bodies)
  4. copy slim outputs to ./data/samples/
  5. union across all per-country JSONLs -> all_wikidata.{parquet,map.html,map.png}
  6. push everything to the HF dataset

Usage:
    uv run python scripts/process_countries.py                # process every country
    uv run python scripts/process_countries.py liechtenstein  # process one country
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import polars as pl

from osm_polygon_to_wikipedia_articles.wikipedia.process_countries import (
    plan_country_run,
    validate_country_outputs,
    ValidationReport,
)
from osm_polygon_to_wikipedia_articles.wikipedia.union import (
    discover_per_country_jsonls,
    union_jsonls,
)
from osm_polygon_to_wikipedia_articles.wikipedia.map import build_map
from osm_polygon_to_wikipedia_articles.wikipedia.render import render_map_png

HF_REPO = "NoeFlandre/osm-polygon-to-wikipedia-articles"
SOURCE_REPO = "NoeFlandre/osm-polygon-selection"
LANG = "en"
SLEEP_S = 0.05

DATA_ROOT = Path(os.environ.get("OSM_DATA_ROOT", "data")).resolve()
SAMPLES_ROOT = Path("data/samples").resolve()


def _hf_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
    return env


def sample_country(country: str, out_path: Path, timeout_s: int = 600) -> None:
    """Sample a country parquet (full country, n=10_000_000 to avoid the cap)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        return
    cmd = [
        "uv", "run", "python", "scripts/sample.py",
        "--countries", country, "--n", "10000000",
        "--out", str(out_path),
    ]
    proc = subprocess.Popen(cmd, start_new_session=True)
    try:
        proc.wait(timeout=timeout_s)
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
    except subprocess.TimeoutExpired:
        print(f"  sample timeout after {timeout_s}s, killing process group {proc.pid}")
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raise


def match_country(in_path: Path, parquet_out: Path, jsonl_out: Path, map_html_out: Path, timeout_s: int = 1500) -> None:
    """Run the Wikidata match pipeline, killing the entire process group on timeout."""
    parquet_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "uv", "run", "python", "scripts/match_wikidata.py",
        "--in", str(in_path),
        "--parquet", str(parquet_out),
        "--jsonl", str(jsonl_out),
        "--map", str(map_html_out),
        "--lang", LANG,
        "--only-wikidata",
        "--sleep", str(SLEEP_S),
        "--max-workers", "8",
    ]
    # Start the child as the leader of a new process group so we can killpg on timeout.
    proc = subprocess.Popen(cmd, start_new_session=True)
    try:
        proc.wait(timeout=timeout_s)
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
    except subprocess.TimeoutExpired:
        print(f"  timeout after {timeout_s}s, killing process group {proc.pid}")
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raise


def copy_to_samples(plan) -> None:
    """Copy the slim outputs from $OSM_DATA_ROOT into ./data/samples/."""
    for src, dst in [
        (plan.match_parquet, plan.samples_match_parquet),
        (plan.match_jsonl, plan.samples_match_jsonl),
        (plan.match_map_html, plan.samples_match_map_html),
        (plan.match_map_png, plan.samples_match_map_png),
    ]:
        if not src.exists():
            print(f"  WARN: missing source {src}, skipping copy to {dst}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def union_all() -> tuple[Path, Path, Path]:
    """Union every per-country *_wikidata.jsonl into the all_wikidata artifacts."""
    jsonls = discover_per_country_jsonls(SAMPLES_ROOT)
    if not jsonls:
        print("no per-country JSONLs found in samples/, skipping union")
        return SAMPLES_ROOT / "all_wikidata.parquet", SAMPLES_ROOT / "all_wikidata_map.html", SAMPLES_ROOT / "all_wikidata_map.png"

    out_parquet = SAMPLES_ROOT / "all_wikidata.parquet"
    out_html = SAMPLES_ROOT / "all_wikidata_map.html"
    out_png = SAMPLES_ROOT / "all_wikidata_map.png"

    df = union_jsonls(jsonls, out_parquet)
    build_map(df, out_path=out_html)
    render_map_png(out_html, out_png, width=1000, height=600)
    print(f"unioned {len(jsonls)} countries -> {df.height} rows")
    return out_parquet, out_html, out_png


def push_to_hf() -> None:
    """Upload every file in ./data/samples/ to the HF dataset."""
    subprocess.run(
        [
            "hf", "upload", HF_REPO, str(SAMPLES_ROOT),
            "--repo-type=dataset",
            "--include", "*",
        ],
        env=_hf_env(),
        check=True,
    )


def process_one(country: str, *, timeout_s: int = 300) -> tuple[str, "ValidationReport"]:
    plan = plan_country_run(country, DATA_ROOT, SAMPLES_ROOT)
    print(f"\n=== {country} ===")
    print(f"  source: {plan.source}")
    sample_country(country, plan.source, timeout_s=timeout_s)
    try:
        match_country(plan.source, plan.match_parquet, plan.match_jsonl, plan.match_map_html, timeout_s=timeout_s)
    except subprocess.TimeoutExpired:
        print(f"  !! match timed out after {timeout_s}s, skipping {country}")
        return country, ValidationReport(ok=False, skipped=True, errors=[f"match timed out after {timeout_s}s"])
    except subprocess.CalledProcessError as exc:
        print(f"  !! match subprocess failed: {exc}")
        return country, ValidationReport(ok=False, errors=[str(exc)])
    copy_to_samples(plan)

    report = validate_country_outputs(plan)
    print(f"  rows={report.n_rows} geometry_missing={report.geometry_wkt_missing} bodies={report.articles_with_body} jsonl={report.jsonl_count} map_html={report.map_html_size}B")
    if not report.ok:
        print(f"  !! VALIDATION FAILED: {report.errors}")
    else:
        print(f"  OK")
    return country, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("countries", nargs="*", help="Countries to process (default: all)")
    parser.add_argument("--skip-union", action="store_true")
    parser.add_argument("--skip-hf", action="store_true")
    parser.add_argument(
        "--per-step-timeout",
        type=int,
        default=600,
        help="Seconds to allow for sample or match step before bailing out (default: 600)",
    )
    args = parser.parse_args()

    # When no countries given, get the list from the source dataset on HF
    countries = list(args.countries)
    if not countries:
        from huggingface_hub import HfApi
        api = HfApi()
        files = api.list_repo_files(repo_id=SOURCE_REPO, repo_type="dataset")
        all_slugs = sorted(
            Path(f).stem
            for f in files
            if f.endswith(".parquet") and "/" not in Path(f).stem
        )
        # Skip aggregate files like "all_europe" — those are pre-merged, not countries
        countries = [c for c in all_slugs if not c.startswith("all_")]

    print(f"OSM_DATA_ROOT = {DATA_ROOT}")
    print(f"SAMPLES_ROOT  = {SAMPLES_ROOT}")
    print(f"countries     = {len(countries)}")
    print(f"per-step timeout: {args.per_step_timeout}s")

    succeeded = []
    failed = []
    for country in countries:
        try:
            c, report = process_one(country, timeout_s=args.per_step_timeout)
            if report.ok and not report.skipped:
                succeeded.append(c)
            elif report.skipped:
                print(f"  (skipped: no matches for {c})")
            else:
                failed.append(c)
                # continue to next country (don't abort on a single failure)
        except Exception as exc:
            print(f"\nEXCEPTION for {country}: {exc}")
            failed.append(c)

    print(f"\n=== summary ===")
    print(f"  succeeded: {len(succeeded)} -> {succeeded}")
    print(f"  failed:    {len(failed)} -> {failed}")

    if not args.skip_union:
        print("\n=== union ===")
        union_all()

    if not args.skip_hf:
        print("\n=== push to HF ===")
        push_to_hf()
        print(f"uploaded to https://huggingface.co/datasets/{HF_REPO}")


if __name__ == "__main__":
    main()