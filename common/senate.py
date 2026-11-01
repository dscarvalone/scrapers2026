"""Combine every county's results into one file: the 2026 U.S. Senate race,
itemized by vote method.

Reads counties/<county>/data/summary_wide.csv (what the election-night
workflow commits) and writes:

    results/senate_by_method.csv       one row per county x candidate x method
    results/senate_by_method_wide.csv  one row per county x candidate, a column per method

Usage:
    python -m common.senate                  # from committed data/ files
    python -m common.senate --from-output    # from local output/*_latest.csv runs
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COUNTIES_DIR = ROOT / "counties"
RESULTS_DIR = ROOT / "results"

SENATE_RE = re.compile(r"\b(u\.?\s*s\.?|united\s+states)\s+senat", re.I)

# Candidates on the ballot. Party is fixed here because some feeds omit it.
CANDIDATES = {
    "sherrod brown": ("Sherrod Brown", "Democratic"),
    "jon husted": ("Jon Husted", "Republican"),
    "greg levy": ("Greg Levy", "Other-party"),
    "william b. redpath": ("William B. Redpath", "Libertarian"),
    "write-in": ("Write-in", ""),
}

# County vote-type labels -> common method names. Labels not listed here are
# kept as-is (e.g. Cuyahoga's "Post Election Day" and "Post VBM").
METHOD_MAP = {
    "Election Day": "Election Day",
    "Early In-Person": "Early In-Person",  # Cuyahoga
    "Early Voting": "Early In-Person",     # Ohio ENR XML (separate from mail)
    "Vote By Mail": "Mail",                # Cuyahoga
    "Mail Ballots": "Mail",                # Ohio ENR XML
    "Provisional": "Provisional",
    "Absentee": "Absentee (early in-person + mail)",  # Ohio ENR CSV, not split
}
METHOD_ORDER = [
    "Election Day", "Early In-Person", "Mail",
    "Absentee (early in-person + mail)", "Provisional",
]

# Columns in a county's wide file that are not vote methods.
NON_METHOD_COLS = {
    # Cuyahoga
    "contest_id", "office", "choice_id", "choice", "party", "row_type", "total",
    # Ohio ENR
    "race_id", "race", "vote_for", "contestant_id", "contestant", "write_in",
    "withdrawn", "pct", "winner", "race_total_votes", "ballots_cast",
    "over_votes", "under_votes", "blank_voted", "precincts_reported",
    "precincts_total", "generated_at", "source_format", "precinct",
}


def county_rows(county: str, path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        return []
    race_col = "office" if "office" in rows[0] else "race"
    name_col = "choice" if "choice" in rows[0] else "contestant"
    methods = [c for c in rows[0] if c not in NON_METHOD_COLS]

    senate = [r for r in rows if SENATE_RE.search(r[race_col])]
    races = {r[race_col] for r in senate}
    if len(races) != 1:
        raise RuntimeError(f"{county}: expected 1 U.S. Senate race, found {sorted(races) or 'none'}")

    out = []
    for r in senate:
        if r.get("row_type", "candidate") != "candidate":
            continue  # Cuyahoga's Ballots Cast / Over / Under rows
        key = " ".join(r[name_col].split()).lower()
        if key not in CANDIDATES:
            raise RuntimeError(f"{county}: unexpected Senate candidate {r[name_col]!r}")
        name, party = CANDIDATES[key]
        method_sum = 0
        for m in methods:
            votes = int(r[m] or 0)
            method_sum += votes
            out.append({
                "county": county.title(),
                "candidate": name,
                "party": party,
                "method": METHOD_MAP.get(m, m),
                "method_county_label": m,
                "votes": votes,
                "precincts_reported": r.get("precincts_reported", ""),
                "precincts_total": r.get("precincts_total", ""),
                "source_generated_at": r.get("generated_at", ""),
            })
        if method_sum != int(r["total"] or 0):
            print(f"WARNING {county} / {name}: methods sum to {method_sum}, county total {r['total']}",
                  file=sys.stderr)
    return out


def to_wide(long_rows: list[dict]):
    methods_seen = []
    for r in long_rows:
        if r["method"] not in methods_seen:
            methods_seen.append(r["method"])
    methods = [m for m in METHOD_ORDER if m in methods_seen] + [m for m in methods_seen if m not in METHOD_ORDER]
    wide: dict[tuple, dict] = {}
    for r in long_rows:
        key = (r["county"], r["candidate"])
        w = wide.setdefault(key, {
            "county": r["county"], "candidate": r["candidate"], "party": r["party"],
            "precincts_reported": r["precincts_reported"], "precincts_total": r["precincts_total"],
            "source_generated_at": r["source_generated_at"],
        })
        w[r["method"]] = w.get(r["method"], 0) + r["votes"]
    for w in wide.values():
        for m in methods:
            w.setdefault(m, "")  # blank = county doesn't report this method
        w["total"] = sum(v for m in methods if isinstance(v := w[m], int))
    fields = ["county", "candidate", "party", *methods, "total",
              "precincts_reported", "precincts_total", "source_generated_at"]
    return fields, list(wide.values())


def write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-output", action="store_true", help="Read local output/summary_wide_latest.csv files")
    ap.add_argument("--out", type=Path, default=RESULTS_DIR)
    args = ap.parse_args(argv)

    rel = Path("output/summary_wide_latest.csv") if args.from_output else Path("data/summary_wide.csv")
    long_rows, used, missing, failed = [], [], [], []
    for d in sorted(p for p in COUNTIES_DIR.iterdir() if p.is_dir() and not p.name.startswith("_")):
        path = d / rel
        if not path.exists():
            missing.append(d.name)
            continue
        try:
            long_rows += county_rows(d.name, path)
            used.append(d.name)
        except Exception as e:
            failed.append(d.name)
            print(f"ERROR {d.name}: {e}", file=sys.stderr)

    write_csv(args.out / "senate_by_method.csv",
              ["county", "candidate", "party", "method", "method_county_label", "votes",
               "precincts_reported", "precincts_total", "source_generated_at"], long_rows)
    fields, wide = to_wide(long_rows)
    write_csv(args.out / "senate_by_method_wide.csv", fields, wide)

    print(f"Senate results from {len(used)} counties: {', '.join(used) or 'none'}", file=sys.stderr)
    if missing:
        print(f"No data yet: {', '.join(missing)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
