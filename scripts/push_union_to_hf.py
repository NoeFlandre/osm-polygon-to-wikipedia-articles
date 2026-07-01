#!/usr/bin/env python
"""Just push union parquet + jsonl + readme to HF (smaller, faster).

Skips the bulky country-by-country parquets/jsonls/maps which are already
on HF from the previous push — this commit overlays the new union (which
has the ``thumbnail_is_svg`` column added) and the country parquets that
were re-tagged with the new column.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from huggingface_hub import HfApi

REPO = "NoeFlandre/osm-polygon-to-wikipedia-articles"


def main() -> int:
    api = HfApi()
    samples = Path("data/samples")

    # 1. Upload the union parquet + jsonl (most important — has new column)
    union_pq = samples / "all_wikidata.parquet"
    if union_pq.exists():
        print(f"uploading {union_pq}")
        api.upload_file(
            path_or_fileobj=str(union_pq),
            path_in_repo="all_wikidata.parquet",
            repo_id=REPO,
            repo_type="dataset",
            commit_message="feat: add thumbnail_is_svg column (SVG detector via .svg / .svg.png leaf token)",
        )

    # 2. Push the in-progress Poland data (it has new column too if available)
    poland_pq = Path("/Volumes/Seagate M3/osm-polygon-to-wikipedia-articles/poland_wikidata.parquet")
    if poland_pq.exists() and Path(samples / "poland_wikidata.parquet").exists():
        print(f"uploading {samples / 'poland_wikidata.parquet'} (poland)")
        api.upload_file(
            path_or_fileobj=str(samples / "poland_wikidata.parquet"),
            path_in_repo="poland_wikidata.parquet",
            repo_id=REPO,
            repo_type="dataset",
        )

    # 3. Update thumbnail columns for all 45 country parquets in samples (overlays the old ones on HF)
    for p in sorted(samples.glob("*_wikidata.parquet")):
        if p.name.startswith("all_"):
            continue
        print(f"uploading {p.name}")
        try:
            api.upload_file(
                path_or_fileobj=str(p),
                path_in_repo=p.name,
                repo_id=REPO,
                repo_type="dataset",
            )
        except Exception as e:
            print(f"  failed: {e}")
            continue

    # 4. Upload JSONLs (note: these are ~50-200KB each, small)
    for p in sorted(samples.glob("*_wikidata.jsonl")):
        if p.name.startswith("all_"):
            continue
        print(f"uploading {p.name}")
        try:
            api.upload_file(
                path_or_fileobj=str(p),
                path_in_repo=p.name,
                repo_id=REPO,
                repo_type="dataset",
            )
        except Exception as e:
            print(f"  failed: {e}")
            continue

    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
