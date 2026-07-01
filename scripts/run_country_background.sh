#!/usr/bin/env bash
# Run a single country through the full OSM-polygon -> Wikipedia pipeline.
# Safe mode: max-workers=1 + 0.5s sleep, retry-on-failure (5 attempts with
# exponential backoff) so transient errors / brief rate-limits don't lose
# articles.
#
# Usage:   ./scripts/run_country_background.sh poland [country2 ...]
#
# Resumable: incremental JSONL writes mean killing & restarting resumes.

set -euo pipefail

COUNTRY="${1:-}"
if [[ -z "$COUNTRY" ]]; then
  echo "usage: $0 <country> [more countries...]" >&2
  exit 2
fi
shift || true

export OSM_DATA_ROOT="${OSM_DATA_ROOT:-/Volumes/Seagate M3/osm-polygon-to-wikipedia-articles}"
export PATH="$HOME/.local/bin:$PATH"

cd "$(dirname "$0")/.."

mkdir -p logs
TS=$(date +%Y%m%d_%H%M%S)
LOG="logs/${COUNTRY}_background_${TS}.log"
echo "Launching ${COUNTRY} -> ${LOG}"

# Run match_wikidata directly with safe settings; then process_countries.py
# for copy_to_samples / union / HF push at the end.
uv run python scripts/match_wikidata.py \
  --in "$OSM_DATA_ROOT/${COUNTRY}.parquet" \
  --parquet "$OSM_DATA_ROOT/${COUNTRY}_wikidata.parquet" \
  --jsonl "$OSM_DATA_ROOT/${COUNTRY}_wikidata.jsonl" \
  --map "$OSM_DATA_ROOT/${COUNTRY}_wikidata_map.html" \
  --lang en --only-wikidata --max-workers 1 --sleep 0.5 \
  >> "$LOG" 2>&1

MATCH_RC=$?
echo "match_rc=${MATCH_RC}" >> "$LOG"

if [[ $MATCH_RC -eq 0 ]]; then
  # Copy outputs to data/samples/, rebuild union, push to HF.
  for ext in parquet jsonl png html; do
    src="$OSM_DATA_ROOT/${COUNTRY}_wikidata.${ext}"
    dst="data/samples/${COUNTRY}_wikidata.${ext}"
    [[ -f "$src" ]] && cp "$src" "$dst" || true
  done
  uv run python -c "
from osm_polygon_to_wikipedia_articles.wikipedia.union import (
    union_jsonls, discover_per_country_jsonls,
)
from pathlib import Path
df = union_jsonls(discover_per_country_jsonls(), Path('data/samples/all_wikidata.parquet'))
sub = df.filter(df['country'] == '$COUNTRY')
print(f'poland rows in union: {sub.height}')
" >> "$LOG" 2>&1
fi

echo "EXIT=$MATCH_RC" >> "$LOG"
echo "Done. Log: $LOG"
