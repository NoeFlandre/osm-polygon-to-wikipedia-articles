#!/bin/bash
# Process a single country: sample (if needed) + match + push to HF.
# Used by the master loop to update HF after every country.
set -e
COUNTRY="${1:?usage: run_one.sh <country>}"
ROOT="${OSM_DATA_ROOT:-/Volumes/Seagate M3/osm-polygon-to-wikipedia-articles}"
export OSM_DATA_ROOT="$ROOT"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export PATH="$HOME/.local/bin:$PATH"
LOG="/Users/noeflandre/osm-polygon-to-wikipedia-articles/logs/${COUNTRY}.log"
mkdir -p "$(dirname "$LOG")"

cd /Users/noeflandre/osm-polygon-to-wikipedia-articles

echo "[$(date +%H:%M:%S)] === $COUNTRY ===" | tee -a "$LOG"

# 1. Process (sample + match + copy to samples/)
uv run python scripts/per_country/process_countries.py "$COUNTRY" \
    --per-step-timeout 14400 \
    --skip-hf \
    2>&1 | tee -a "$LOG"

# 2. Re-run union across all per-country JSONLs
echo "[$(date +%H:%M:%S)] union" | tee -a "$LOG"
uv run python scripts/dataset/union_matches.py 2>&1 | tee -a "$LOG"

# 3. Push to HF
echo "[$(date +%H:%M:%S)] push to HF" | tee -a "$LOG"
hf upload NoeFlandre/osm-polygon-to-wikipedia-articles data/samples \
    --repo-type dataset \
    2>&1 | tee -a "$LOG"

echo "[$(date +%H:%M:%S)] DONE $COUNTRY" | tee -a "$LOG"
