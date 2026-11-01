#!/usr/bin/env bash
# Open the Chrome window that common/sos_browser.py reads SOS ENR files through.
#
# - Separate, empty profile (~/.scrapers2026-chrome): none of your normal
#   Chrome logins, cookies or history.
# - Debugging port bound to 127.0.0.1 only. While it's open, any program on
#   this Mac could control THIS window (not your normal Chrome), so keep
#   nothing signed in here and close it when done.
# - If the page shows "Verify you are human", complete it like any visitor.
#   The scripts never touch the check.
#
# Run from Terminal (an agent sandbox can't start Chrome). Leave the window open.
set -eu
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE="$HOME/.scrapers2026-chrome"
PORT="${SOS_CDP_PORT:-9333}"
[ -x "$CHROME" ] || { echo "Google Chrome not found at $CHROME"; exit 1; }
if curl -s --max-time 2 "http://127.0.0.1:$PORT/json/version" >/dev/null; then
  echo "A Chrome debugging port is already open on 127.0.0.1:$PORT; using it."; exit 0
fi
mkdir -p "$PROFILE"
"$CHROME" --remote-debugging-address=127.0.0.1 --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" --no-first-run --no-default-browser-check \
  "https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/en/Index_24.html" >/dev/null 2>&1 &
echo "Chrome started (debugging on 127.0.0.1:$PORT, profile $PROFILE). Keep the window open."
