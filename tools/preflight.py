"""Before the loop starts: make sure each SOS site loads in the scrapers2026
Chrome window without a Cloudflare check.

One request per site, 3 s apart, through the window's own tabs:
  liveresults.boe.ohio.gov   SOS results feed (Butler, Lucas, Stark, ...)
  www.boe.ohio.gov           SOS-hosted county PDFs (Licking, Erie, Miami, ...)
  liveresults.ohiosos.gov    statewide totals
If a site shows a check, its tab is brought to the front, a notification
pops up, and this waits (rechecking every 15 s) until the person clicks
"Verify you are human" there. It never touches the check itself.

Exit 0 when all three are clear, 1 if one is still blocked after --wait minutes.

Usage:
    python -m tools.preflight [--wait 10]
"""

from __future__ import annotations

import argparse
import base64
import sys
import time
import urllib.request

from common import sos_browser as sb
from tools.run_sos_counties import TAB_HINT, notify

SITES = [
    ("liveresults.boe.ohio.gov", "https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/en/Index_24.html",
     "https://liveresults.boe.ohio.gov/ENR/butlerohenr/24/summary_24.xml"),
    ("www.boe.ohio.gov", "https://www.boe.ohio.gov/licking/election-info/election-results/",
     "https://www.boe.ohio.gov/licking/c/elecres/20261103results.pdf"),
    ("liveresults.ohiosos.gov", "https://liveresults.ohiosos.gov/", "https://liveresults.ohiosos.gov/"),
]


def blocked(page, probe: str) -> bool:
    r = page.evaluate(sb._JS_BYTES, probe)
    head = base64.b64decode(r["b64"])[:5000].decode("utf-8", "ignore")
    return sb._is_challenge(r["status"], r["type"], head) or r["status"] in (403, 503)


def wait_for_port(seconds: int = 30) -> bool:
    for _ in range(seconds):
        try:
            urllib.request.urlopen(f"{sb.CDP_URL}/json/version", timeout=2).read()
            return True
        except OSError:
            time.sleep(1)
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=float, default=10, help="minutes to wait for a person to clear a check")
    args = ap.parse_args(argv)
    if not wait_for_port():
        print("PREFLIGHT: the scrapers2026 Chrome window isn't open (run tools/sos_chrome.sh).", file=sys.stderr)
        return 1
    br = sb.shared()
    bad = []
    for host, page_url, probe in SITES:
        page = br.tab_for(page_url)
        time.sleep(sb.PAUSE)
        if not blocked(page, probe):
            print(f"PREFLIGHT ok: {host}", file=sys.stderr)
            continue
        hint = TAB_HINT.get(host, host)
        print(f"PREFLIGHT: Cloudflare check on {host}. Click 'Verify you are human' in {hint} "
              f"(brought to the front). Waiting up to {args.wait:g} min...", file=sys.stderr)
        page.bring_to_front()
        notify("Election scraper: click Verify", f"Cloudflare check on {host}. The tab is in front.")
        deadline = time.monotonic() + args.wait * 60
        while time.monotonic() < deadline:
            time.sleep(15)
            if not blocked(page, probe):
                print(f"PREFLIGHT ok: {host} (cleared)", file=sys.stderr)
                break
        else:
            bad.append(host)
            print(f"PREFLIGHT: {host} still blocked; its counties will be skipped until it's cleared.",
                  file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
