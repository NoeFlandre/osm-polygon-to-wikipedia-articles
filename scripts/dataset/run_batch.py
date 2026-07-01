#!/usr/bin/env python3
"""Run multiple countries end-to-end with the batched pipeline.

Sequential: each country finishes (incl. parquet write + README + HF push)
before the next starts.  This keeps the load on Wikipedia predictable
and gives us a clean log per country.

Usage:
    uv run python scripts/dataset/run_batch.py <country1> [country2 ...]
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run_one(country: str, workers: int) -> int:
    """Run the full pipeline for one country. Returns 0 on success."""
    samples_dir = Path("data/samples/per_country") / country
    log_dir = Path("logs/per_country")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Move existing shipped files to a backup so we always have a
    # "before" copy if anything goes wrong.
    backup_root = Path("data/samples.backup_batch")
    backup_root.mkdir(exist_ok=True)
    if samples_dir.exists():
        backup = backup_root / country
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(samples_dir, backup)
        print(f"[batch] backed up {samples_dir} -> {backup}")
        shutil.rmtree(samples_dir)

    samples_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{country}_{ts}.log"

    print(f"[batch] starting {country} (workers={workers}, log={log_path})", flush=True)
    t0 = time.time()

    # 1. Rerun the batched pipeline.
    rc = subprocess.run(
        ["uv", "run", "python",
         "scripts/per_country/rerun_country_batched.py",
         country, "--workers", str(workers)],
        check=False,
    ).returncode
    if rc != 0:
        print(f"[batch] {country} rerun_country_batched failed rc={rc}", flush=True)
        return rc
    print(f"[batch] {country} rerun done in {time.time()-t0:.0f}s", flush=True)

    # 2. Finish (add_thumbnail_columns, README, HF push).
    rc = subprocess.run(
        ["uv", "run", "python",
         "scripts/dataset/finish_and_push_country.py", country],
        check=False,
    ).returncode
    if rc != 0:
        print(f"[batch] {country} finish_and_push failed rc={rc}", flush=True)
        return rc
    print(f"[batch] {country} done in {time.time()-t0:.0f}s total", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("countries", nargs="+")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    failed = []
    for c in args.countries:
        rc = run_one(c, args.workers)
        if rc != 0:
            failed.append((c, rc))
    if failed:
        print(f"[batch] FAILED: {failed}")
        return 1
    print(f"[batch] all {len(args.countries)} countries done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
