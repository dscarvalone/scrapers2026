"""Run every SOS-ENR county scraper in one process, over one connection to
the Chrome window (tools/sos_chrome.sh), and copy each county's output to
counties/<name>/data/summary_wide.csv. That's what the Actions workflow
commits for its own counties, and what common/senate.py reads.

A county that fails (a changed URL, a stale election ID) is reported and
skipped; the others still run. Exit code 1 if any failed.

Usage:
    python -m tools.run_sos_counties              # all generated SOS counties
    python -m tools.run_sos_counties stark clark  # just these folders
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from common.ohio_enr import run
from common.senate import save_senate_only

ROOT = Path(__file__).resolve().parent.parent
DISCOVERY = ROOT / "tools" / "enr_discovery.json"


def sos_folders() -> list[str]:
    """SOS ENR counties from discovery, plus any scraper that declares
    NEEDS_LOCAL_CHROME = True (e.g. county PDFs on SOS-hosted BOE sites)."""
    found = json.loads(DISCOVERY.read_text())
    folders = {c.lower().replace(" ", "_") for c, r in found.items() if r.get("election_id")}
    for p in (ROOT / "counties").glob("*/scraper.py"):
        if "NEEDS_LOCAL_CHROME = True" in p.read_text():
            folders.add(p.parent.name)
    return sorted(folders)


def host_of(mod) -> str:
    """The site a county scraper reads from (its URL/URLS/PAGE/RESULTS_PAGE/BASE)."""
    for attr in ("URL", "URLS", "PAGE", "RESULTS_PAGE", "BASE"):
        v = getattr(mod, attr, None)
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None
        if isinstance(v, str) and v:
            return urlparse(v).netloc
    return ""


TAB_HINT = {
    "liveresults.boe.ohio.gov": "the 'Election Night Results' tab (SOS results feed)",
    "www.boe.ohio.gov": "the 'Election Results – LICKING COUNTY' tab (SOS county PDFs)",
    "liveresults.ohiosos.gov": "the 'Ohio Decides' tab (statewide totals)",
}


def notify(title: str, text: str) -> None:
    """macOS notification, best effort (never fails the run)."""
    try:
        subprocess.run(["osascript", "-e", f"display notification {json.dumps(text)} with title {json.dumps(title)} "
                        "sound name \"Glass\""], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def main(argv=None) -> int:
    folders = (argv if argv is not None else sys.argv[1:]) or sos_folders()
    ok, failed, skipped = [], [], []
    blocked: dict[str, str] = {}   # host -> reason; later counties on that host are skipped this cycle
    for f in folders:
        mod = importlib.import_module(f"counties.{f}.scraper")
        out = ROOT / "counties" / f / "output"
        name = f.replace("_", " ").title()
        host = host_of(mod)
        if host in blocked:
            skipped.append(f)
            continue
        try:
            if hasattr(mod, "main"):
                if mod.main([]) not in (0, None):
                    raise RuntimeError("scraper reported a problem (see above)")
            else:
                run(name, mod.URLS, out, argv=[], expect_year="2026")
            latest = out / "summary_wide_latest.csv"
            if not latest.exists():
                # e.g. Allen before its election-night link is posted
                print(f"{f}: no data yet", file=sys.stderr)
                continue
            # Commit the U.S. Senate race only (the scraper reads the whole feed).
            save_senate_only(latest, ROOT / "counties" / f / "data" / "summary_wide.csv")
            ok.append(f)
        except (Exception, SystemExit) as e:
            failed.append(f)
            print(f"ERROR {f}: {e}", file=sys.stderr)
            msg = str(e)
            # A Cloudflare check or rate limit on one site means every later
            # county on THAT site fails the same way: skip them this cycle
            # (don't hammer the host), but keep going with the other sites.
            if "Cloudflare check" in msg:
                blocked[host] = "Cloudflare check"
                hint = TAB_HINT.get(host, host)
                print(f"BLOCKED {host}: Cloudflare check. Click 'Verify you are human' in {hint} of the "
                      "scrapers2026 Chrome window; skipping its other counties this cycle.", file=sys.stderr)
                notify("Election scraper: click Verify", f"Cloudflare check on {host}. Open {hint}.")
            elif "rate limited" in msg.lower():
                blocked[host] = "rate limited"
                print(f"BLOCKED {host}: rate limited; skipping its other counties this cycle.", file=sys.stderr)
            elif "No Chrome debugging port" in msg:
                for h in TAB_HINT:   # every SOS site needs the window; other hosts carry on
                    blocked[h] = "Chrome window not open"
                print("BLOCKED SOS sites: the Chrome window isn't open (run tools/sos_chrome.sh).", file=sys.stderr)
                notify("Election scraper", "SOS Chrome window isn't open. Run tools/sos_chrome.sh.")
    print(f"SOS ENR counties: {len(ok)} ok, {len(failed)} failed"
          + (f" ({', '.join(failed)})" if failed else "")
          + (f", {len(skipped)} skipped ({', '.join(skipped)}) behind: "
             + "; ".join(f"{h} {r}" for h, r in blocked.items()) if skipped else ""), file=sys.stderr)
    return 1 if failed or skipped else 0


if __name__ == "__main__":
    sys.exit(main())
