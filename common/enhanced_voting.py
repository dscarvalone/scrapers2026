"""Parser for Enhanced Voting public results (app.enhancedvoting.com), used by
Ohio counties such as Montgomery.

Source: the JSON the public results page itself loads:
    https://app.enhancedvoting.com/results/public/api/elections/<Jurisdiction>/<ElectionId>/data
Each candidate has a total and "groupResults", which are vote-method buckets.
Montgomery, Nov 2026: Absentee, Early Voting, Election Day, Provisional, plus
"Absentee Add-In", "Early Voting Add-In", "Election Day Add-In" (votes added
after election night). Group names are kept exactly as the county labels
them; common/senate.py maps them.

Plain HTTP; no Cloudflare check (tested 2026-11-01), so this also runs in
GitHub Actions.

Output (same shape as the other scrapers): output/summary_wide_latest.csv,
one row per race and choice, a column per vote group, and a total, with a
check that the groups sum to the total.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

API = "https://app.enhancedvoting.com/results/public/api/elections/{jur}/{eid}/data"
UA = {"User-Agent": "scrapers2026 (election results research)"}
BASE = ["race_id", "race", "contestant", "party", "write_in"]
TAIL = ["total", "precincts_reported", "precincts_total", "generated_at", "source_format"]
PARTY_PREFIX = re.compile(r"^(DEM|REP|LIB|OPC|GRN|NON|IND|NPA|OTH|CON|SOC|NAT)\s+(.+)$", re.I)
# Pickaway lists write-ins individually ("Write-in: Stephen Faris",
# "Write-in: Not Assigned", "Write-in: -Invalid-"). They're summed into one
# Write-in line; "-Invalid-" ones are left out of it.
WRITE_IN = re.compile(r"^write-?in\b", re.I)
INVALID = re.compile(r"invalid", re.I)


def _en(v) -> str:
    """Enhanced Voting stores text as [{languageId, text}]."""
    if isinstance(v, list):
        for x in v:
            if x.get("languageId") == "en":
                return (x.get("text") or "").strip()
        return (v[0].get("text") or "").strip() if v else ""
    return str(v or "").strip()


def parse(data: dict) -> tuple[dict, list[dict], list[str]]:
    gen = data.get("election", {}).get("asOf", "")
    rows, groups = [], []
    for item in data.get("ballotItems") or []:
        race = _en(item.get("name"))
        rs = item.get("reportingStatus") or {}
        merged: dict[str, dict] = {}
        for opt in (item.get("summaryResults") or {}).get("ballotOptions") or []:
            raw = " ".join(_en(opt.get("name")).split())
            if WRITE_IN.match(raw) and INVALID.search(raw):
                continue
            m = PARTY_PREFIX.match(raw)
            name = m.group(2) if m else raw
            if WRITE_IN.match(name):
                name = "Write-in"
            row = merged.get(name)
            if row is None:
                row = merged[name] = {
                    "race_id": item.get("id", ""),
                    "race": race,
                    "contestant": name,
                    "party": m.group(1).upper() if m else ((opt.get("party") or {}).get("abbreviation") or ""),
                    "write_in": name == "Write-in" or bool(opt.get("isWriteIn")),
                    "total": 0,
                    "precincts_reported": rs.get("reportingUnits", ""),
                    "precincts_total": rs.get("totalUnits", ""),
                    "generated_at": gen,
                    "source_format": "enhanced_voting",
                }
            row["total"] += int(opt.get("voteCount") or 0)
            for g in opt.get("groupResults") or []:
                gname = _en(g.get("groupName"))
                if gname not in groups:
                    groups.append(gname)
                row[gname] = row.get(gname, 0) + int(g.get("voteCount") or 0)
        rows.extend(merged.values())
    for r in rows:
        for g in groups:
            r.setdefault(g, 0)
    return {"generated_at": gen}, rows, groups


def check(rows, groups) -> list[str]:
    return [f"{r['race']} / {r['contestant']}: groups sum to {sum(r[g] for g in groups)}, total {r['total']}"
            for r in rows if sum(r[g] for g in groups) != r["total"]]


def run(county: str, jurisdiction: str, election_id: str, out_dir: Path, argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"{county} County, OH results by vote type (Enhanced Voting)")
    ap.add_argument("--out", type=Path, default=out_dir)
    args = ap.parse_args(argv)
    url = API.format(jur=jurisdiction, eid=election_id)
    print(f"Downloading {url}", file=sys.stderr)
    r = requests.get(url, headers=UA, timeout=60, params={"v": int(time.time() * 1000)})
    r.raise_for_status()
    meta, rows, groups = parse(r.json())
    if not rows:
        raise SystemExit(f"{county}: no ballot items in {url}")
    print(f"{county}: enhanced_voting feed, {len(rows)} rows, {len({x['race'] for x in rows})} races, "
          f"generated {meta['generated_at']}", file=sys.stderr)
    problems = check(rows, groups)
    if problems:
        print(f"WARNING: {len(problems)} rows where vote groups don't sum to the total:", file=sys.stderr)
        for p in problems[:10]:
            print("  " + p, file=sys.stderr)
    else:
        print("Vote-type sums match totals.", file=sys.stderr)
    fields = BASE + groups + TAIL
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.out.mkdir(parents=True, exist_ok=True)
    for name in (f"summary_wide_{stamp}.csv", "summary_wide_latest.csv"):
        with (args.out / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    print(f"Wrote {len(rows):,} rows -> {args.out / 'summary_wide_latest.csv'}", file=sys.stderr)
    return 0
