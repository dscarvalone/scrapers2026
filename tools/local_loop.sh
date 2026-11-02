#!/usr/bin/env bash
# Election-night loop for the sources GitHub Actions can't reach.
#
# Why this runs on a desktop: the SOS sites block GitHub's runners (manual
# workflow run, 2026-11-01). From the owner's Mac they work:
#   - SOS-hosted county ENR feeds (vote-method split): through the Chrome
#     window opened by tools/sos_chrome.sh. Skipped, with a warning, if that
#     window isn't open.
#   - SOS statewide site (county totals, all 88): headed Playwright Chromium.
#
# Every INTERVAL seconds:
#   1. python -m tools.run_sos_counties  -> counties/<name>/data/summary_wide.csv
#   2. python -m common.ohio_statewide   -> results/senate_statewide_by_county.csv
#      (each file is rewritten only when its numbers changed)
#   2b. python -m common.timing -> results/statewide_snapshots.csv (appended on
#      change; the first-drop estimate needs this time series, so DON'T lose
#      it) and results/senate_by_timing.csv (before vs on Election Day)
#   3. commit just those files if changed; git pull --rebase (every cycle); git push
#   4. python -m tools.build_method_workbook $EXPORT_DIR  -> the standalone
#      vote-method workbook + CSVs (outside the repo; not committed)
# The Actions bot commits Cuyahoga/Franklin and rebuilds the combined
# results/senate_by_method_wide.csv from everything committed, on its next run.
#
# Usage, from the repo root, in a normal Terminal window:
#   tools/sos_chrome.sh                    # first: open the SOS Chrome window
#   tools/local_loop.sh                    # asks for a GitHub token once, runs until END
#   DRY_RUN=1 ONCE=1 tools/local_loop.sh   # one cycle, no commit/pull/push
#
# Settings (environment variables):
#   INTERVAL  seconds between cycles               (default 300)
#   END       stop time, America/New_York           (default "2026-11-04 08:00")
#   BRANCH    branch to push                        (default main)
#   DRY_RUN=1 fetch only; no git writes
#   ONCE=1    run one cycle and exit
#   GH_TOKEN  GitHub token; if unset, prompted for (hidden) at start
#   EXPORT_DIR  where the vote-method workbook goes   (default ../exports)
#   BUILD_SHEET=0  skip the workbook build (and the Google Sheet update)
#   GSHEET_ID   your own Google Sheet's ID: each cycle replaces its GSHEET_TAB
#               tab (default "methods") with county_results.csv (tools/push_sheet.py)
#
# The token is held only in this process's environment and passed to git
# per command. It is never written to git config, the keychain or a file.
# The Mac is kept awake with caffeinate while the loop runs. Ctrl-C to stop.

set -u
cd "$(dirname "$0")/.." || exit 1

INTERVAL="${INTERVAL:-300}"
END="${END:-2026-11-04 08:00}"
BRANCH="${BRANCH:-main}"
DRY_RUN="${DRY_RUN:-0}"
ONCE="${ONCE:-0}"
FILE="results/senate_statewide_by_county.csv"
PY="${PY:-.venv/bin/python}"
# Never pop up a temporary browser for the statewide fetch: without the SOS
# Chrome window it logs a warning instead (common/ohio_statewide.py).
export SOS_REQUIRE_WINDOW=1
EXPORT_DIR="${EXPORT_DIR:-../exports}"
BUILD_SHEET="${BUILD_SHEET:-1}"

log() { echo "[$(TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

# Files this loop commits: the statewide CSV plus every county data file
# except those of counties the Actions bot scrapes (COUNTIES in the workflow).
owned_files() {
  local bot f c
  bot=$(sed -n 's/^ *COUNTIES: *"\(.*\)".*/\1/p' .github/workflows/election-night.yml)
  [ -f "$FILE" ] && echo "$FILE"
  for f in results/statewide_snapshots.csv results/senate_by_timing.csv; do
    [ -f "$f" ] && echo "$f"
  done
  for f in counties/*/data/summary_wide.csv; do
    [ -f "$f" ] || continue
    c=${f#counties/}; c=${c%%/*}
    case " $bot " in
      *" $c "*) ;;
      *) echo "$f" ;;
    esac
  done
}

end_epoch=$(TZ=America/New_York date -j -f "%Y-%m-%d %H:%M" "$END" +%s 2>/dev/null) || {
  echo "Bad END value: $END (expected YYYY-MM-DD HH:MM)"; exit 1; }
[ -x "$PY" ] || { echo "No Python at $PY (create the venv: see README)"; exit 1; }

if [ "$DRY_RUN" != "1" ]; then
  if [ -z "${GH_TOKEN:-}" ]; then
    read -rs -p "GitHub token (input hidden): " GH_TOKEN; echo
  fi
  [ -n "$GH_TOKEN" ] || { echo "No token given"; exit 1; }
  AUTH="Authorization: Basic $(printf 'x-access-token:%s' "$GH_TOKEN" | base64)"
  unset GH_TOKEN
  export GIT_TERMINAL_PROMPT=0   # fail fast instead of hanging on a prompt
  git_net() { git -c http.extraheader="$AUTH" "$@"; }
  # Catch auth problems now, not at the first real push.
  if ! git_net ls-remote --exit-code origin "refs/heads/$BRANCH" >/dev/null; then
    echo "Can't reach origin/$BRANCH with that token (check it's valid and has"
    echo "Contents: Read and write on this repo)."; exit 1
  fi
  log "Token OK. Syncing with origin/$BRANCH first."
  git_net pull --rebase --autostash -q origin "$BRANCH" || { echo "Initial pull failed"; exit 1; }
fi

# Keep the Mac awake for as long as this script runs.
caffeinate -dims -w $$ &

log "Starting: every ${INTERVAL}s until $END ET$([ "$DRY_RUN" = 1 ] && echo ' (DRY RUN)')"
while :; do
  # 1. County scrapers that run locally: SOS ENR feeds and SOS-hosted PDFs (via
  #    the Chrome window), plus Hamilton and Clermont (plain HTTP). If the
  #    window is closed or a site shows a Cloudflare check, only that site's
  #    counties are skipped; the rest still run.
  curl -s --max-time 3 "http://127.0.0.1:${SOS_CDP_PORT:-9333}/json/version" >/dev/null \
    || log "WARNING: SOS Chrome window not open (run tools/sos_chrome.sh); SOS counties will be skipped."
  "$PY" -m tools.run_sos_counties || log "WARNING: some counties failed or were skipped (see above)."
  # 2. Statewide county totals (all 88, no method split).
  "$PY" -m common.ohio_statewide || log "ERROR: statewide fetch failed (see above)."
  # 2b. Before vs on Election Day: append the statewide snapshot (the time
  #     series the first-drop estimate needs) and rebuild results/senate_by_timing.csv.
  "$PY" -m common.timing || log "WARNING: timing model reported errors (see above)."

  if [ "$DRY_RUN" = "1" ]; then
    log "Dry run: skipping git."
  else
    # Only the files this loop owns. Cuyahoga/Franklin are the bot's.
    # Skip counties the Actions bot scrapes (COUNTIES in the workflow).
    owned=$(owned_files)
    [ -n "$owned" ] && git add $owned
    if git diff --cached --quiet; then
      log "No change in results."
    else
      changed=$(git diff --cached --name-only | sed -e 's#^counties/\([^/]*\)/.*#\1#' -e 's#^results/.*#statewide#' | sort -u | tr '\n' ' ')
      git commit -q -m "Local results update (${changed% }) $(TZ=America/New_York date '+%Y-%m-%d %H:%M %Z')"
      log "Committed: $changed"
    fi
      # Pull every cycle, not only when pushing, so the Actions bot's counties
      # are current for the vote-method workbook built below.
      git_net pull --rebase --autostash -q origin "$BRANCH" || log "WARNING: pull failed; workbook may lag the bot's counties."
      # Push whenever we're ahead of origin, including a commit left over
      # from a cycle whose push failed.
      if [ "$(git rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null || echo 1)" != "0" ]; then
        pushed=0
        for attempt in 1 2 3; do   # the bot may push between our pull and push
          if git_net pull --rebase --autostash -q origin "$BRANCH" && git_net push -q origin "HEAD:$BRANCH"; then
            pushed=1; break
          fi
          log "Push attempt $attempt failed; retrying in 10s."; sleep 10
        done
        [ "$pushed" = 1 ] && log "Pushed." || log "ERROR: could not push; will retry next cycle."
      fi
  fi

  # 4. Standalone vote-method workbook (xlsx + CSVs) for the Google Sheet.
  #    Written outside the repo, never committed. A failure here never stops
  #    the loop.
  if [ "$BUILD_SHEET" = "1" ]; then
    "$PY" -m tools.build_method_workbook "$EXPORT_DIR" 2>&1 | sed 's/^/    /'
    if [ "${PIPESTATUS[0]}" = "0" ]; then
      log "Workbook refreshed: $EXPORT_DIR/OH_Senate_2026_vote_method.xlsx"
    else
      log "WARNING: workbook build reported errors (see above); files hold whatever parsed."
    fi
  fi

  # 5. Optional: copy county_results.csv into one tab of the owner's own
  #    Google Sheet (set GSHEET_ID; see README "Google Sheet updates").
  if [ "$BUILD_SHEET" = "1" ] && [ -n "${GSHEET_ID:-}" ]; then
    "$PY" -m tools.push_sheet "$EXPORT_DIR/county_results.csv" 2>&1 | sed 's/^/    /'
    [ "${PIPESTATUS[0]}" = "0" ] || log "WARNING: Google Sheet update failed (see above); will retry next cycle."
  fi

  [ "$ONCE" = "1" ] && break
  now=$(date +%s)
  if [ "$now" -ge "$end_epoch" ]; then log "Reached $END ET; stopping."; break; fi
  sleep "$INTERVAL"
done
