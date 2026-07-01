#!/usr/bin/env python
"""Add ``thumbnail_is_svg`` column to every per-country parquet and the union,
rebuild the union, and push the updated dataset to Hugging Face.

Safe to re-run: detects existing column, drops it before re-adding so we
always overwrite with the current logic.

Logged to ``logs/thumbnail_push_<ts>.log`` for resumable auditing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import polars as pl

from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.thumbnail import (
    THUMBNAIL_IS_SVG,
    add_thumbnail_columns,
)
from osm_polygon_to_wikipedia_articles.wikipedia.pipeline.union import (
    discover_per_country_jsonls,
    union_jsonls,
)

SAMPLES = Path("data/samples")


def log(msg: str) -> None:
    print(f"[{datetime.utcnow().isoformat()}] {msg}", flush=True)


def add_to_parquet(p: Path) -> tuple[int, int]:
    """Return (rows_before, rows_after); no-op if column already present."""
    df = pl.read_parquet(p)
    before = df.height
    if THUMBNAIL_IS_SVG in df.columns:
        df = df.drop(THUMBNAIL_IS_SVG)
    out = add_thumbnail_columns(df)
    out.write_parquet(p)
    return before, out.height


def main() -> int:
    log_file = Path("logs") / f"thumbnail_push_{int(time.time())}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    tee = open(log_file, "w")
    class _Tee:
        def __init__(self, *streams):
            self._streams = streams
        def write(self, s):
            for st in self._streams:
                st.write(s)
            return len(s)
        def flush(self):
            for st in self._streams:
                st.flush()
    sys.stdout = _Tee(sys.__stdout__, tee)
    sys.stderr = _Tee(sys.__stderr__, tee)

    log("=== add_thumbnail_column_and_push ===")

    # 1. Update every per-country parquet in data/samples/
    parquets = sorted(SAMPLES.glob("*_wikidata.parquet"))
    parquets = [p for p in parquets if not p.name.startswith("all_")]
    log(f"per-country parquets: {len(parquets)}")
    svg_totals: dict[str, int] = {}
    for p in parquets:
        try:
            before, _ = add_to_parquet(p)
            df2 = pl.read_parquet(p)
            svg_count = int(df2[THUMBNAIL_IS_SVG].sum() or 0)
            svg_totals[p.stem.replace("_wikidata", "")] = svg_count
            log(f"  {p.name}: {before} rows, {svg_count} SVG thumbnails")
        except Exception as e:
            log(f"  {p.name}: FAILED ({e})")

    # 2. Rebuild union from JSONLs
    jsonls = discover_per_country_jsonls(SAMPLES)
    log(f"per-country JSONLs: {len(jsonls)}")
    union_path = SAMPLES / "all_wikidata.parquet"
    df_union = union_jsonls(jsonls, union_path)
    log(f"union: {df_union.height} rows, {df_union['country'].n_unique()} countries")

    # 3. Add thumbnail_is_svg to union
    if THUMBNAIL_IS_SVG in df_union.columns:
        df_union = df_union.drop(THUMBNAIL_IS_SVG)
    df_union = add_thumbnail_columns(df_union)
    df_union.write_parquet(union_path)
    svg_union = int(df_union[THUMBNAIL_IS_SVG].sum() or 0)
    log(f"union SVG flags: {svg_union} / {df_union.height}")

    # 4. Push to HF — invoke the SAME push_to_hf() that process_countries uses,
    # but as a subprocess so we don't re-process every country.
    log("invoking push_to_hf via subprocess (hf upload only, no per-country re-run) ...")
    env = {
        **os.environ,
        "OSM_DATA_ROOT": "/Volumes/Seagate M3/osm-polygon-to-wikipedia-articles",
        "PATH": f"{Path.home()}/.local/bin:" + os.environ.get("PATH", ""),
    }
    proc = subprocess.run(
        ["hf", "upload", "NoeFlandre/osm-polygon-to-wikipedia-articles", str(SAMPLES),
         "--repo-type=dataset", "--include", "*"],
        env=env,
        capture_output=True,
        text=True,
    )
    rc = proc.returncode
    log(f"hf upload rc={rc}")
    if proc.stdout.strip():
        log("--- upload stdout ---")
        log(proc.stdout.strip()[-4000:])  # tail to avoid log spam
    if proc.stderr.strip():
        log("--- upload stderr ---")
        log(proc.stderr.strip()[-4000:])
    if rc != 0:
        log("upload FAILED")

    # Summary
    log("\n=== SVG thumbnail summary (top 15 by count) ===")
    for country, count in sorted(svg_totals.items(), key=lambda kv: -kv[1])[:15]:
        log(f"  {country}: {count}")

    log(f"total SVG thumbnails across union: {svg_union} / {df_union.height}")
    log(f"DONE. log: {log_file}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
