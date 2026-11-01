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
import shutil
import sys
from pathlib import Path

from common.ohio_enr import run

ROOT = Path(__file__).resolve().parent.parent
DISCOVERY = ROOT / "tools" / "enr_discovery.json"


def sos_folders() -> list[str]:
    found = json.loads(DISCOVERY.read_text())
    return sorted(c.lower().replace(" ", "_") for c, r in found.items() if r.get("election_id"))


def main(argv=None) -> int:
    folders = (argv if argv is not None else sys.argv[1:]) or sos_folders()
    ok, failed = [], []
    for f in folders:
        mod = importlib.import_module(f"counties.{f}.scraper")
        out = ROOT / "counties" / f / "output"
        name = f.replace("_", " ").title()
        try:
            run(name, mod.URLS, out, argv=[], expect_year="2026")
            shutil.copyfile(out / "summary_wide_latest.csv", ROOT / "counties" / f / "data" / "summary_wide.csv")
            ok.append(f)
        except (Exception, SystemExit) as e:
            # ChallengeNotCleared / RateLimited mean every later county will
            # fail the same way: stop rather than hammer the host.
            failed.append(f)
            print(f"ERROR {f}: {e}", file=sys.stderr)
            msg = str(e)
            if "Cloudflare check" in msg or "rate limited" in msg.lower() or "No Chrome debugging port" in msg:
                print("Stopping: fix the browser window / wait, then rerun.", file=sys.stderr)
                break
    print(f"SOS ENR counties: {len(ok)} ok, {len(failed)} failed"
          + (f" ({', '.join(failed)})" if failed else ""), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
