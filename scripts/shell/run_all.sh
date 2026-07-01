#!/bin/bash
# Autonomous master loop: processes every country in order, pushes HF after each.
# Designed to be run in background; logs everything to logs/all_countries.log.
set +e

COUNTRIES=(
  estonia latvia serbia iceland greece hungary france croatia bulgaria
  denmark belgium slovakia lithuania bosnia-herzegovina netherlands switzerland
  portugal belarus romania slovenia austria turkey ukraine czech-republic finland sweden
)

LOG="/Users/noeflandre/osm-polygon-to-wikipedia-articles/logs/all_countries.log"
mkdir -p "$(dirname "$LOG")"
cd /Users/noeflandre/osm-polygon-to-wikipedia-articles

echo "[$(date +%H:%M:%S)] master loop starting; ${#COUNTRIES[@]} countries" >> "$LOG"

SUCCEEDED=()
FAILED=()
SKIPPED=()

for c in "${COUNTRIES[@]}"; do
  echo "[$(date +%H:%M:%S)] >>> $c" >> "$LOG"
  bash scripts/shell/run_one.sh "$c" >> "$LOG" 2>&1
  rc=$?
  echo "[$(date +%H:%M:%S)] <<< $c rc=$rc" >> "$LOG"
  if [ $rc -eq 0 ]; then
    SUCCEEDED+=("$c")
  else
    FAILED+=("$c")
  fi
done

echo "" >> "$LOG"
echo "[$(date +%H:%M:%S)] === master summary ===" >> "$LOG"
echo "succeeded (${#SUCCEEDED[@]}): ${SUCCEEDED[*]}" >> "$LOG"
echo "failed    (${#FAILED[@]}): ${FAILED[*]}" >> "$LOG"
echo "[$(date +%H:%M:%S)] DONE" >> "$LOG"
