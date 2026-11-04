#!/bin/bash
# Fallback for the GitHub Actions bot: scrape its counties (COUNTIES in the
# workflow) on this Mac every 5 minutes, with the same commands the workflow
# runs, so counties/<c>/data/summary_wide.csv stays current for the local
# loop's workbook and Google Sheet push. Does NOT commit: tools/local_loop.sh
# leaves the bot's files to the bot. Stop with: pkill -f bot_counties_local.sh
cd "$(dirname "$0")/.."
PY="${PY:-.venv/bin/python}"
COUNTIES=$(sed -n 's/^ *COUNTIES: *"\(.*\)".*/\1/p' .github/workflows/election-night.yml)
END="${END:-2026-11-04 08:00}"
end_epoch=$(TZ=America/New_York date -j -f "%Y-%m-%d %H:%M" "$END" +%s)
while [ "$(date +%s)" -lt "$end_epoch" ]; do
  for c in $COUNTIES; do
    "$PY" -m counties.$c.scraper >/dev/null 2>&1 && "$PY" -m tools.save_senate $c >/dev/null 2>&1 \
      && echo "[$(TZ=America/New_York date '+%H:%M:%S')] $c ok" || echo "[$(TZ=America/New_York date '+%H:%M:%S')] $c FAILED"
    sleep 1
  done
  sleep "${INTERVAL:-300}"
done
