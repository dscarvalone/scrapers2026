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
# - Opens in the BACKGROUND (open -g): it doesn't take focus from what you're
#   doing. The scripts reuse its tabs and open any new one in the background,
#   so it never comes to the front by itself. You can minimize it or move it
#   to another Desktop: the flags below stop Chrome from pausing a hidden
#   window, so fetches keep working.
# - Starts with the three tabs the loop needs: the SOS ENR feed, the SOS
#   statewide site, and an SOS-hosted BOE page (for county PDFs).
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
# open -g: launch without bringing Chrome to the front. -n: a separate Chrome
# instance (this profile), not a new window in your everyday Chrome.
open -g -n -a "Google Chrome" --args \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE" --no-first-run --no-default-browser-check \
  --disable-background-timer-throttling --disable-renderer-backgrounding \
  --disable-backgrounding-occluded-windows \
  "https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/en/Index_24.html" \
  "https://liveresults.ohiosos.gov/" \
  "https://www.boe.ohio.gov/licking/election-info/election-results/"
up=0
for _ in $(seq 1 20); do
  if curl -s --max-time 1 "http://127.0.0.1:$PORT/json/version" >/dev/null; then up=1; break; fi
  sleep 1
done
if [ "$up" != 1 ]; then
  echo "Chrome did not open its debugging port on 127.0.0.1:$PORT within 20 s."
  echo "Run this from a normal Terminal window (an agent sandbox can't start Chrome). If a"
  echo "scrapers2026 Chrome is already open WITHOUT the port, quit that one and rerun."
  exit 1
fi
echo "Chrome started in the background (debugging on 127.0.0.1:$PORT, profile $PROFILE)."
echo "Check its tabs once for a 'Verify you are human' box, then minimize it or leave it behind your work."
