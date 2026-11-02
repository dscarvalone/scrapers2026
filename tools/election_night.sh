#!/usr/bin/env bash
# Election night in one command.
#
#   tools/election_night.sh          # the real loop: until 8 AM ET Nov 4, commits + pushes,
#                                    # updates the Google Sheet (asks for a GitHub token once)
#   tools/election_night.sh --test   # one cycle, no git writes (still updates the sheet)
#
# It: pulls the latest code/data, opens the scrapers2026 Chrome window in the
# background (or reuses it), checks the three SOS sites for a Cloudflare check
# and waits for you to click it if needed, then runs tools/local_loop.sh with
# your Google Sheet set. Run it from a normal Terminal window.
#
# Settings: GSHEET_ID (default: the owner's "scarv E-night" sheet; GSHEET_ID= to skip
# the sheet), plus everything tools/local_loop.sh accepts (INTERVAL, END, ...).
set -u
cd "$(dirname "$0")/.." || exit 1
PY="${PY:-.venv/bin/python}"
export GSHEET_ID="${GSHEET_ID-1jCzz-0RdSDOpIiAh_5Gx8RX5pahF6I2WstewfCAbuVs}"

if [ "${1:-}" = "--test" ]; then
  export DRY_RUN=1 ONCE=1
  echo "== Test run: one cycle, no git writes"
  # (The real loop pulls on its own once it has your token.)
  git pull -q --ff-only 2>/dev/null && echo "== Pulled latest" || echo "== git pull skipped (no access or local changes); continuing"
else
  echo "== Election night loop (Ctrl-C to stop)"
fi

echo "== Chrome window"
tools/sos_chrome.sh || exit 1

echo "== Checking the SOS sites for a 'Verify you are human' box"
"$PY" -m tools.preflight || echo "== WARNING: a site is still blocked; its counties are skipped until you clear it (the loop keeps trying)"

exec tools/local_loop.sh
