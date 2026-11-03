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
    # Franklin's ENR reports "Early Voting" and "Absentee Ballots" side by
    # side. Early in-person voting is its own column, so "Absentee Ballots"
    # is the mailed-ballot count. ASSUMPTION, inferred from the column
    # structure, not from a county definition; see REPORT.md.
    "Absentee Ballots": "Mail",
    # SOS-hosted ENR (e.g. Butler): Early Voting / Absentee Voting / Election
    # Day / Provisional. The ENR page's own hidden setting hdnMailVote has the
    # value "Absentee Voting", so the software itself calls this column the
    # mail vote.
    "Absentee Voting": "Mail",
    "Early In Person": "Early In-Person",  # Stark
    "Vote by Mail": "Mail",               # Stark
    "Absentee Walk-in": "Early In-Person",  # Summit (in-person absentee = early voting)
    "Absentee Mail": "Mail",                # Summit
    # Summit's "Timely Absentee" is deliberately NOT mapped: likely mail
    # ballots received after Election Day, but not confirmed. Passes through
    # as its own column.
    # County PDF reports (common/pdf_results.py):
    "Absentee Office": "Early In-Person",  # Licking, Madison (Electionware): in-office absentee = early in-person
    "Absentee Mail": "Mail",                # Licking, Madison, Van Wert, Preble
    "Absentee Mail Out": "Mail",            # Athens
    "Absentee In Office": "Early In-Person",  # Athens
    "Absentee In - Person": "Early In-Person",  # Clermont (positional parser joins "In-Person" with spaces)
    "Absentee In-Person": "Early In-Person",    # Clermont, if the hyphen extracts intact
    "Absentee Early": "Early In-Person",    # Preble
    # Preble's "Absentee Late" (likely mail ballots arriving after Election
    # Day) is deliberately left unmapped, like Summit's Timely Absentee.
    # Hamilton (Clarity): only "Election" and "Early". "Early" isn't defined
    # on the site as mail-only or in-person-only, so it goes in the combined
    # absentee bucket rather than guessing.
    "Election": "Election Day",
    "Early": "Absentee (early in-person + mail)",
    "AB": "Mail",                           # Miami (Dominion): absentee, next to a separate EV column
    "ED": "Election Day",                   # Miami
    "EV": "Early In-Person",                # Miami
    "PR": "Provisional",                    # Miami
}
# Counties with no county-level scraper get their total from the statewide
# SOS site (common/ohio_statewide.py), which has no method split. Their votes
# go in this column so the wide file's total stays right and it's obvious the
# split is missing.
UNSPLIT = "Not split by method"
STATEWIDE_CSV = RESULTS_DIR / "senate_statewide_by_county.csv"

# Enhanced Voting feeds (common/enhanced_voting.py, e.g. Montgomery) report
# "Absentee" NEXT TO a separate "Early Voting" group, so there it means mail,
# unlike the ENR CSV's combined "Absentee". Checked first for those rows.
# The "... Add-In" groups (votes added after election night) are left
# unmapped, like Cuyahoga's Post Election Day / Post VBM.
EV_METHOD_MAP = {
    "Absentee": "Mail",
    "Early Voting": "Early In-Person",
    "Election Day": "Election Day",
    "Provisional": "Provisional",
    # Summit (Enhanced Voting, Nov 2026). "Timely Abs" is left unmapped,
    # like the Timely Absentee column in Summit's older ENR schema.
    "Abs Mail": "Mail",
    "Polls": "Election Day",
    "Abs Walk-in": "Early In-Person",
    "In Office Absentee": "Early In-Person",  # Pickaway
    "Mail Absentee": "Mail",                  # Pickaway
}

# Per-county overrides, for labels that mean different things in different
# counties. Keyed by county folder name.
COUNTY_METHOD_MAP = {
    # Seneca's Nov 2026 report has Election Day / Absentee / Provisional /
    # Early Vote. With early in-person in its own column, "Absentee" is the
    # mailed ballots (ASSUMPTION, as for Franklin and Clark).
    # (The positional parser labels the "Early Vote" column "Early".)
    "seneca": {"Absentee": "Mail", "Early": "Early In-Person", "Early Vote": "Early In-Person"},
    # Greene (Enhanced Voting, Nov 2026): Polling / Polling Paper / Early
    # Voting / Absentee / Provisional. Both "Polling" groups are ballots cast
    # at the polling place on Election Day (paper = hand-counted/emergency).
    "greene": {"Polling": "Election Day", "Polling Paper": "Election Day"},
}

METHOD_ORDER = [
    "Election Day", "Early In-Person", "Mail",
    "Absentee (early in-person + mail)", "Provisional", UNSPLIT,
]

# Columns in a county's wide file that are not vote methods.
NON_METHOD_COLS = {
    # Cuyahoga
    "contest_id", "office", "choice_id", "choice", "party", "row_type", "total",
    # Ohio ENR
    "race_id", "race", "vote_for", "contestant_id", "contestant", "write_in",
    "withdrawn", "pct", "winner", "race_total_votes", "ballots_cast",
    "over_votes", "under_votes", "blank_voted", "precincts_reported",
    "precincts_total", "generated_at", "source_format", "precinct", "write_in_detail",
}


# The candidates the checks are about. A county update that lacks either one,
# or where either one's vote types don't add up to their total, is refused
# (the last good file is kept). Other lines (Levy, Redpath, write-ins) only warn.
REQUIRED = ("Sherrod Brown", "Jon Husted")


def candidate_of(row: dict, name_col: str) -> str | None:
    """Canonical candidate name for a feed row, or None if not a known candidate."""
    key = " ".join((row.get(name_col) or "").split()).lower()
    # Some ENR installs (Franklin) prefix the name with the party code
    # from the party column: "Dem Sherrod Brown", "Opc Greg Levy".
    party_code = (row.get("party") or "").strip().lower()
    if party_code and key.startswith(party_code + " ") and key not in CANDIDATES:
        key = key[len(party_code) + 1:]
    return CANDIDATES[key][0] if key in CANDIDATES else None


def _methods_sum(row: dict, fields: list[str]) -> int:
    return sum(int(row[m] or 0) for m in fields if m not in NON_METHOD_COLS)


def check_senate_rows(rows: list[dict], fields: list[str], where: str) -> list[str]:
    """Hard problems with Brown and Husted (raise on these); prints warnings
    for the other candidates. `rows` are one county's Senate-race rows."""
    name_col = "choice" if "choice" in fields else "contestant"
    cands = [r for r in rows if r.get("row_type", "candidate") == "candidate"]
    seen: dict[str, dict] = {}
    problems = []
    for r in cands:
        name = candidate_of(r, name_col)
        if name is None:
            problems.append(f"unexpected Senate candidate {r.get(name_col)!r}")
            continue
        try:
            total, msum = int(r["total"] or 0), _methods_sum(r, fields)
        except ValueError as e:
            msg = f"{name}: non-numeric votes ({e})"
            if name in REQUIRED:
                problems.append(msg)
            else:
                print(f"WARNING {where}: {msg}", file=sys.stderr)
            continue
        if msum != total:
            msg = f"{name}: vote types sum to {msum:,}, total is {total:,}"
            if name in REQUIRED:
                problems.append(msg)
            else:
                print(f"WARNING {where}: {msg}", file=sys.stderr)
        seen[name] = r
    missing = [n for n in REQUIRED if n not in seen]
    if missing:
        problems.append(f"missing {' and '.join(missing)}")
    return problems


def save_senate_only(src: Path, dst: Path) -> int:
    """Copy a county's scraper output to its committed data file, keeping only
    the U.S. Senate race (every row of that race, including Cuyahoga's ballots
    cast / over / under rows). Raises, and leaves `dst` untouched, unless the
    file holds exactly one U.S. Senate race with Brown and Husted present and
    each one's vote types adding up to their total. Returns rows kept."""
    with src.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)
    race_col = "office" if "office" in fields else "race"
    keep = [r for r in rows if SENATE_RE.search(r.get(race_col) or "")]
    races = {r[race_col] for r in keep}
    if len(races) != 1:
        raise RuntimeError(f"{src}: expected 1 U.S. Senate race, found {sorted(races) or 'none'}; "
                           f"{dst} left as is")
    problems = check_senate_rows(keep, fields, str(src.parent.parent.name))
    if problems:
        raise RuntimeError(f"{src}: " + "; ".join(problems) + f"; {dst} left as is")
    tmp = dst.with_name(dst.name + ".tmp")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(keep)
    tmp.replace(dst)
    return len(keep)


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

    problems = check_senate_rows(senate, list(rows[0]), county)
    if problems:
        raise RuntimeError(f"{county}: " + "; ".join(problems))

    out = []
    for r in senate:
        if r.get("row_type", "candidate") != "candidate":
            continue  # Cuyahoga's Ballots Cast / Over / Under rows
        name = candidate_of(r, name_col)
        party = next(p for n, p in CANDIDATES.values() if n == name)
        mapping = {**METHOD_MAP, **EV_METHOD_MAP} if r.get("source_format") == "enhanced_voting" else METHOD_MAP
        mapping = {**mapping, **COUNTY_METHOD_MAP.get(county.lower(), {})}
        for m in methods:
            votes = int(r[m] or 0)
            out.append({
                "county": county.replace("_", " ").title(),  # van_wert -> Van Wert
                "candidate": name,
                "party": party,
                "method": mapping.get(m, m),
                "method_county_label": m,
                "votes": votes,
                "precincts_reported": r.get("precincts_reported", ""),
                "precincts_total": r.get("precincts_total", ""),
                "source_generated_at": r.get("generated_at", ""),
                "source": "county_feed",
            })
    return out  # sums already checked above (hard for Brown/Husted, warning for the rest)


def statewide_rows(path: Path, have: set[str]) -> tuple[list[dict], list[str]]:
    """Long rows (method = UNSPLIT) for counties NOT in `have`, plus all
    statewide rows (for cross_check)."""
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    have_req: dict[str, set] = {}
    for r in rows:
        have_req.setdefault(r["county"].strip(), set()).add(r["candidate"])
    gaps = [f"{c} (missing {' and '.join(n for n in REQUIRED if n not in s)})"
            for c, s in have_req.items() if not set(REQUIRED) <= s]
    if gaps or len(have_req) != 88:
        raise RuntimeError(f"statewide: {len(have_req)} counties; Brown/Husted missing in: "
                           + (", ".join(gaps) or "none"))
    out = []
    for r in rows:
        county = r["county"].strip()
        name = r["candidate"]
        if name not in {v[0] for v in CANDIDATES.values()}:
            raise RuntimeError(f"statewide: unexpected candidate {name!r}")
        party = next(p for n, p in CANDIDATES.values() if n == name)
        if county.lower() in have:
            continue
        out.append({
            "county": county, "candidate": name, "party": party,
            "method": UNSPLIT, "method_county_label": "(statewide total)",
            "votes": int(r["votes"] or 0),
            "precincts_reported": r["precincts_reported"], "precincts_total": r["precincts_total"],
            "source_generated_at": r["fetched_at"], "source": "sos_statewide",
        })
    return out, rows


def cross_check(long_rows: list[dict], statewide: list[dict]) -> list[str]:
    feed: dict[tuple, int] = {}
    for r in long_rows:
        if r["source"] == "county_feed":
            k = (r["county"].lower(), r["candidate"])
            feed[k] = feed.get(k, 0) + r["votes"]
    problems = []
    for r in statewide:
        k = (r["county"].strip().lower(), r["candidate"])
        if k in feed and feed[k] != int(r["votes"] or 0):
            tag = "" if r["candidate"] in REQUIRED else " (minor candidate)"
            problems.append(f"{r['county']} / {r['candidate']}{tag}: county feed {feed[k]:,}, "
                            f"statewide {int(r['votes'] or 0):,}")
    # Brown/Husted first: those are the mismatches that matter.
    return sorted(problems, key=lambda p: "(minor candidate)" in p)


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
            "source_generated_at": r["source_generated_at"], "source": r["source"],
        })
        w[r["method"]] = w.get(r["method"], 0) + r["votes"]
    for w in wide.values():
        for m in methods:
            w.setdefault(m, "")  # blank = county doesn't report this method
        w["total"] = sum(v for m in methods if isinstance(v := w[m], int))
    fields = ["county", "candidate", "party", *methods, "total",
              "precincts_reported", "precincts_total", "source", "source_generated_at"]
    return fields, sorted(wide.values(), key=lambda w: (w["county"], list(
        n for n, _ in CANDIDATES.values()).index(w["candidate"])))


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
    ap.add_argument("--statewide", type=Path, default=STATEWIDE_CSV,
                    help="Statewide county totals (from common.ohio_statewide); fills counties "
                         "with no county scraper. Skipped if the file doesn't exist.")
    ap.add_argument("--no-statewide", action="store_true", help="Use county feeds only")
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

    n_statewide = 0
    if not args.no_statewide and args.statewide.exists():
        have = {r["county"].lower() for r in long_rows}
        try:
            extra, statewide = statewide_rows(args.statewide, have)
            for p in cross_check(long_rows, statewide):
                print(f"WARNING county feed vs statewide: {p}", file=sys.stderr)
            long_rows += extra
            n_statewide = len({r["county"] for r in extra})
        except Exception as e:
            failed.append("statewide")
            print(f"ERROR statewide: {e}", file=sys.stderr)

    write_csv(args.out / "senate_by_method.csv",
              ["county", "candidate", "party", "method", "method_county_label", "votes",
               "precincts_reported", "precincts_total", "source", "source_generated_at"], long_rows)
    fields, wide = to_wide(long_rows)
    write_csv(args.out / "senate_by_method_wide.csv", fields, wide)

    print(f"Senate results by method from {len(used)} county feeds: {', '.join(used) or 'none'}",
          file=sys.stderr)
    if n_statewide:
        print(f"Totals only (statewide site, no method split) for {n_statewide} more counties",
              file=sys.stderr)
    if missing:
        print(f"No county-feed data yet: {', '.join(missing)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
