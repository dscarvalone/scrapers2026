#!/usr/bin/env bash
# Election-night loop for the SOS statewide county totals.
#
# Why this runs on a desktop and not in GitHub Actions: the SOS statewide site
# (liveresults.ohiosos.gov) needs a headed browser and still blocks GitHub's
# runners. Confirmed on a manual workflow run, 2026-11-01. From a home
# connection it works. See REPORT.md.
#
# Every INTERVAL seconds:
#   1. python -m common.ohio_statewide   (rewrites the CSV only if numbers changed)
#   2. if results/senate_statewide_by_county.csv changed: commit just that file
#   3. git pull --rebase, then git push   (the Actions bot commits county data
#      and the combined results to the same branch)
# The Actions workflow's combine step reads the committed statewide file, so
# results/senate_by_method_wide.csv picks it up on the bot's next run.
#
# Usage, from the repo root, in a normal Terminal window:
#   tools/statewide_loop.sh                 # asks for a GitHub token once, runs until END
#   DRY_RUN=1 ONCE=1 tools/statewide_loop.sh  # one fetch, no commit/pull/push
#
# Settings (environment variables):
#   INTERVAL  seconds between cycles               (default 300)
#   END       stop time, America/New_York           (default "2026-11-04 08:00")
#   BRANCH    branch to push                        (default main)
#   DRY_RUN=1 fetch only; no git writes
#   ONCE=1    run one cycle and exit
#   GH_TOKEN  GitHub token; if unset, prompted for (hidden) at start
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

log() { echo "[$(TZ=America/New_York date '+%Y-%m-%d %H:%M:%S %Z')] $*"; }

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
  if "$PY" -m common.ohio_statewide; then
    if [ "$DRY_RUN" = "1" ]; then
      log "Dry run: skipping git."
    else
      git add "$FILE"
      if git diff --cached --quiet -- "$FILE"; then
        log "No change in county totals."
      else
        git commit -q -m "Statewide county totals $(TZ=America/New_York date '+%Y-%m-%d %H:%M %Z')" -- "$FILE"
        log "Committed new county totals."
      fi
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
  else
    log "ERROR: statewide fetch failed (see message above); will retry next cycle."
  fi

  [ "$ONCE" = "1" ] && break
  now=$(date +%s)
  if [ "$now" -ge "$end_epoch" ]; then log "Reached $END ET; stopping."; break; fi
  sleep "$INTERVAL"
done
