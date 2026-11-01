"""U.S. Senate results for all 88 Ohio counties from the Secretary of State's
statewide results site, "Ohio Decides" (liveresults.ohiosos.gov).

What it gives: each county's total votes per candidate, plus precincts
reported. What it does NOT give: a split by vote method. The statewide API has
no method fields. The per-county split only exists in each county's ENR
summary XML/CSV (liveresults.boe.ohio.gov), which sits behind a Cloudflare
Turnstile CAPTCHA that this project does not try to solve. So this source fills
in county TOTALS for counties that have no county-level scraper.

How it works: liveresults.ohiosos.gov serves a Cloudflare check to plain HTTP
clients and to headless browsers (both confirmed 2026-11-01). A normal,
headed Chromium passes the automatic check. This module opens the site in
one, then makes the same API request the site's own page makes when you open
the "U.S. Senator" tab and choose county results. That's two requests per run
for the whole state. If Cloudflare shows a challenge that doesn't clear on its
own, it stops and reports that rather than trying to get around it.
(The project's no-bypass rule was waived by the owner for this; see REPORT.md.)

Needs: `pip install playwright` and `python -m playwright install chromium`,
plus a display, so a desktop session. On Linux CI use `xvfb-run`.

Usage:
    python -m common.ohio_statewide                # fetch live, write results/
    python -m common.ohio_statewide --file x.json  # parse a saved API response
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "results" / "senate_statewide_by_county.csv"
RAW_DIR = ROOT / "output" / "statewide"  # git-ignored

SITE = "https://liveresults.ohiosos.gov/"
API = "/Api/v1/Contest/GetContestDetailsObject"
CONTEST = "U.S. Senator"
PAUSE = 1.1  # seconds between requests to the same host

# Statewide names -> the project's candidate names (common/senate.py
# CANDIDATES). Certified write-in candidates are listed individually on the
# statewide site, but county feeds report a single "Write-in" line, so they
# are summed into Write-in here.
NAMED = {
    "sherrod brown": "Sherrod Brown",
    "jon husted": "Jon Husted",
    "greg levy": "Greg Levy",
    "william b. redpath": "William B. Redpath",
}

FIELDS = ["county", "candidate", "votes", "precincts_reported", "precincts_total",
          "write_in_detail", "fetched_at"]


class ChallengeNotCleared(RuntimeError):
    pass


def _blocked(title: str, html_head: str) -> bool:
    s = (title + " " + html_head).lower()
    return any(k in s for k in ("just a moment", "security check", "attention required",
                                "website maintenance"))


def fetch_json(headless: bool = False, wait_s: int = 25) -> dict:
    """Open the site in a real browser and return the county-level U.S. Senate
    JSON from the site's own API."""
    from playwright.sync_api import sync_playwright  # optional dependency

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(SITE, timeout=60_000)
            for _ in range(wait_s):
                if not _blocked(page.title(), page.content()[:4000]):
                    break
                time.sleep(1)
            else:
                raise ChallengeNotCleared(
                    f"Cloudflare check on {SITE} did not clear within {wait_s}s "
                    f"(title {page.title()!r}). Not attempting to solve it. "
                    "Headless mode is known to be blocked; run headed.")
            time.sleep(PAUSE)

            def api(params: dict) -> dict:
                res = page.evaluate(
                    """async ([path, params]) => {
                        const r = await fetch(path + '?' + new URLSearchParams(params),
                            {headers: {'Content-Type': 'application/json; charset=utf-8'}});
                        return {status: r.status, type: r.headers.get('content-type'),
                                text: await r.text()};
                    }""", [API, params])
                if res["status"] != 200 or "json" not in (res["type"] or ""):
                    raise RuntimeError(f"API returned {res['status']} {res['type']}: "
                                       f"{res['text'][:200]!r}")
                return json.loads(res["text"])

            # The contest's object ID comes from the summary call, as on the site.
            summary = api({"contestName": CONTEST, "contestObjectId": "",
                           "resultsLevel": "", "countyId": ""})
            oid = summary["contestList"][0]["objectId"]
            time.sleep(PAUSE)
            return api({"contestName": CONTEST, "contestObjectId": oid,
                        "resultsLevel": "County", "countyId": ""})
        finally:
            browser.close()


def parse(data: dict, fetched_at: str) -> list[dict]:
    rows = []
    for county in data.get("contestList") or []:
        name = county["name"].strip()
        totals: dict[str, int] = {}
        write_ins = []
        for c in county["candidatesRunning"]:
            raw = " ".join(c["primaryCandidate"].split())
            votes = int(round(c.get("vCount") if c.get("vCount") is not None
                              else float(str(c.get("voteCount", "0")).replace(",", "") or 0)))
            if c.get("isWriteIn") or c.get("candidateParty") == "WI":
                totals["Write-in"] = totals.get("Write-in", 0) + votes
                write_ins.append(f"{raw}={votes}")
                continue
            key = raw.lower()
            if key not in NAMED:
                raise RuntimeError(f"{name}: unexpected U.S. Senate candidate {raw!r}")
            totals[NAMED[key]] = totals.get(NAMED[key], 0) + votes
        for cand in [*NAMED.values(), "Write-in"]:
            rows.append({
                "county": name,
                "candidate": cand,
                "votes": totals.get(cand, 0),
                "precincts_reported": county.get("reportedPrecincts", ""),
                "precincts_total": county.get("totalPrecincts", ""),
                "write_in_detail": "; ".join(write_ins) if cand == "Write-in" else "",
                "fetched_at": fetched_at,
            })
    counties = {r["county"] for r in rows}
    if len(counties) != 88:
        raise RuntimeError(f"Expected 88 counties, got {len(counties)}")
    return rows


def unchanged(path: Path, rows: list[dict]) -> bool:
    """True if `path` already holds the same numbers (ignoring fetched_at), so
    a polling loop doesn't commit a new file every cycle."""
    if not path.exists():
        return False
    key = lambda rs: [tuple(str(r[f]) for f in FIELDS if f != "fetched_at") for r in rs]
    with path.open(encoding="utf-8") as f:
        return key(list(csv.DictReader(f))) == key(rows)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="Parse a saved API JSON response instead of fetching")
    ap.add_argument("--headless", action="store_true", help="Run headless (known to be blocked)")
    ap.add_argument("--out", type=Path, default=OUT_CSV)
    args = ap.parse_args(argv)

    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if args.file:
        data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        print(f"Opening {SITE} in Chromium ({'headless' if args.headless else 'headed'})", file=sys.stderr)
        data = fetch_json(headless=args.headless)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (RAW_DIR / f"senate_county_{stamp}.json").write_text(json.dumps(data), encoding="utf-8")

    rows = parse(data, fetched_at)
    reporting = sum(1 for r in rows if r["candidate"] == "Write-in" and r["precincts_reported"] not in ("", 0, "0"))
    total = sum(r["votes"] for r in rows)
    summary = f"Statewide U.S. Senate: 88 counties, {total:,} votes, {reporting} counties with precincts reporting"
    if unchanged(args.out, rows):
        # fetched_at in the file is when these numbers were first seen.
        print(f"{summary} (unchanged; {args.out} left as is)", file=sys.stderr)
    else:
        write_csv(args.out, rows)
        print(f"{summary} -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
