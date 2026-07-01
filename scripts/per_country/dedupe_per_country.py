"""Dedupe per-country *_wikidata.parquet and *_wikidata.jsonl on (osm_id, country).

Some source country parquets (e.g. france) contain the same logical polygon
under multiple records sharing an (osm_id, country) key. The match pipeline
preserves those duplicates 1:1, inflating row counts. This script picks the
first occurrence per key for each per-country output.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

SAMPLES = Path("/Users/noeflandre/osm-polygon-to-wikipedia-articles/data/samples")
KEYS = ["osm_id", "country"]


def dedupe_parquet(path: Path) -> int:
    df = pl.read_parquet(path)
    before = df.height
    df = df.unique(subset=KEYS, keep="first")
    after = df.height
    if before != after:
        df.write_parquet(path)
    return before - after


def dedupe_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    seen: set[tuple[int, str]] = set()
    before_lines = 0
    kept: list[str] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        before_lines += 1
        rec = json.loads(line)
        key = (rec["osm_id"], rec["country"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(line)
    removed = before_lines - len(kept)
    if removed:
        path.write_text("\n".join(kept) + ("\n" if kept else ""))
    return removed


def main() -> None:
    total_removed = 0
    for pq in sorted(SAMPLES.glob("*_wikidata.parquet")):
        if pq.stem == "all_wikidata":
            continue
        removed = dedupe_parquet(pq)
        if removed:
            print(f"  {pq.name}: removed {removed} duplicate rows")
            total_removed += removed
    for jl in sorted(SAMPLES.glob("*_wikidata.jsonl")):
        if jl.stem == "all_wikidata":
            continue
        removed = dedupe_jsonl(jl)
        if removed:
            print(f"  {jl.name}: removed {removed} duplicate lines")
            total_removed += removed
    print(f"total removed: {total_removed}")


if __name__ == "__main__":
    main()
