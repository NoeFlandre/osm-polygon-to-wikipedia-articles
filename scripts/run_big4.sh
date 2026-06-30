#!/bin/bash
# Re-process the 4 large countries that timed out at 3600s.
# Each: process_countries + run_one.sh handles sample/match/copy
# After all 4: re-run enrichment on the new per-country parquets,
# re-run union, push to HF.
set +e

COUNTRIES=(
  slovakia ukraine czech-republic sweden
)

LOG="/Users/noeflandre/osm-polygon-to-wikipedia-articles/logs/big4.log"
mkdir -p "$(dirname "$LOG")"
cd /Users/noeflandre/osm-polygon-to-wikipedia-articles

echo "[$(date +%H:%M:%S)] big4 starting" >> "$LOG"

for c in "${COUNTRIES[@]}"; do
  echo "[$(date +%H:%M:%S)] >>> $c" >> "$LOG"
  bash scripts/run_one.sh "$c" >> "$LOG" 2>&1
  rc=$?
  echo "[$(date +%H:%M:%S)] <<< $c rc=$rc" >> "$LOG"
done

echo "[$(date +%H:%M:%S)] re-enriching union" >> "$LOG"
uv run python scripts/enrich_with_input_columns.py >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] pushing to HF" >> "$LOG"
export PATH="$HOME/.local/bin:$PATH"
hf upload NoeFlandre/osm-polygon-to-wikipedia-articles data/samples \
    --repo-type dataset >> "$LOG" 2>&1

echo "[$(date +%H:%M:%S)] DONE" >> "$LOG"
