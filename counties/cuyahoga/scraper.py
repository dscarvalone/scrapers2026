"""Cuyahoga County (OH) election results, broken down by vote type.

The county publishes an "All Results" Excel export (hosted by Enhanced Voting).
Its "... by Group" sheets split every contest/choice into vote types:
Election Day, Early In-Person, Vote By Mail, Provisional, Post Election Day,
and Post VBM.

Usage:
    python -m counties.cuyahoga.scraper                      # county totals, download live file
    python -m counties.cuyahoga.scraper --precincts          # also precinct-level (slow, ~1M rows)
    python -m counties.cuyahoga.scraper --file results.xlsx  # parse a local copy instead
    python -m counties.cuyahoga.scraper --long               # one row per vote type instead of wide

Outputs go to counties/cuyahoga/output/ (git-ignored).
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests
from openpyxl import load_workbook

DEFAULT_URL = (
    "https://app.enhancedvoting.com/cdn/results/"
    "6397b9a7-ccfa-406e-a155-6d2a595cf70d/"
    "All%20Results_6c376c4d-15e5-4aec-83b0-0e4cfeec59cb.xlsx"
)

SUMMARY_SHEET = "Summary Results"
SUMMARY_GROUP_SHEET = "Summary Results by Group"
PRECINCT_GROUP_SHEET = "Precinct Results by Group"

# Order used for wide-format columns. Unknown groups are appended at the end.
VOTE_TYPE_ORDER = [
    "Election Day",
    "Early In-Person",
    "Vote By Mail",
    "Provisional",
    "Post Election Day",
    "Post VBM",
]

SPECIAL_ROWS = {"Ballots Cast", "Over Votes", "Under Votes"}

OUT_DIR = Path(__file__).resolve().parent / "output"


def clean(text) -> str:
    """Strip HTML line breaks, tabs and repeated whitespace from a cell."""
    if text is None:
        return ""
    text = re.sub(r"<br\s*/?>", " ", str(text), flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def fetch(url: str) -> bytes:
    resp = requests.get(
        url,
        timeout=120,
        headers={"User-Agent": "scrapers2026 (election results research)"},
    )
    resp.raise_for_status()
    if not resp.content.startswith(b"PK"):
        raise RuntimeError(
            f"Response from {url} is not an .xlsx file "
            f"(content-type: {resp.headers.get('content-type')}). "
            "The file URL may have changed."
        )
    return resp.content


def iter_sheet(wb, sheet_name: str):
    """Yield each row of a sheet as a dict keyed by its header row.

    The export pads every row with ~70 empty columns, so we only keep columns
    that have a header.
    """
    if sheet_name not in wb.sheetnames:
        raise KeyError(f"Sheet {sheet_name!r} not found; sheets are {wb.sheetnames}")
    rows = wb[sheet_name].iter_rows(values_only=True)
    header = [clean(h) for h in next(rows)]
    width = max(i for i, h in enumerate(header) if h) + 1
    header = header[:width]
    for row in rows:
        row = row[:width]
        if all(v in (None, "") for v in row):
            continue
        yield dict(zip(header, row))


def to_record(row: dict, precinct: bool) -> dict:
    ballot_name = clean(row.get("Ballot Name"))
    rec = {
        "contest_id": clean(row.get("Contest ID")),
        "office": clean(row.get("Office Name")),
        "choice_id": clean(row.get("Choice ID")),
        "choice": ballot_name,
        "party": clean(row.get("Party")),
        "row_type": (
            ballot_name.lower().replace(" ", "_")
            if ballot_name in SPECIAL_ROWS
            else "candidate"
        ),
        "vote_type": clean(row.get("Group")),
        "votes": int(row.get("Total") or 0),
    }
    if precinct:
        rec = {"precinct": clean(row.get("Precinct")), **rec}
    return rec


def parse(wb, sheet_name: str, precinct: bool) -> list[dict]:
    return [to_record(r, precinct) for r in iter_sheet(wb, sheet_name)]


def to_wide(records: list[dict]) -> tuple[list[str], list[dict]]:
    """Pivot long records into one row per contest/choice with a column per vote type."""
    key_fields = [k for k in records[0] if k not in ("vote_type", "votes")] if records else []
    seen_types = []
    rows: dict[tuple, dict] = {}
    for rec in records:
        vt = rec["vote_type"]
        if vt not in seen_types:
            seen_types.append(vt)
        key = tuple(rec[k] for k in key_fields)
        row = rows.setdefault(key, {k: rec[k] for k in key_fields})
        row[vt] = row.get(vt, 0) + rec["votes"]

    vote_types = [t for t in VOTE_TYPE_ORDER if t in seen_types] + [
        t for t in seen_types if t not in VOTE_TYPE_ORDER
    ]
    out = []
    for row in rows.values():
        for vt in vote_types:
            row.setdefault(vt, 0)
        row["total"] = sum(row[vt] for vt in vote_types)
        out.append(row)
    return key_fields + vote_types + ["total"], out


def check_against_totals(wb, wide_rows: list[dict]) -> list[str]:
    """Compare the vote-type sums with the county's own Summary Results totals."""
    if SUMMARY_SHEET not in wb.sheetnames:
        return ["Summary Results sheet missing; skipped total check."]
    official = {}
    for r in iter_sheet(wb, SUMMARY_SHEET):
        key = (clean(r.get("Contest ID")), clean(r.get("Choice ID")), clean(r.get("Ballot Name")))
        official[key] = int(r.get("Total") or 0)
    problems = []
    for row in wide_rows:
        key = (row["contest_id"], row["choice_id"], row["choice"])
        if key not in official:
            problems.append(f"No official total for {key}")
        elif official[key] != row["total"]:
            problems.append(
                f"{row['office']} / {row['choice']}: vote types sum to "
                f"{row['total']}, official total is {official[key]}"
            )
    return problems


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=DEFAULT_URL, help="Results .xlsx URL")
    ap.add_argument("--file", help="Parse a local .xlsx instead of downloading")
    ap.add_argument("--precincts", action="store_true", help="Also export precinct-level results")
    ap.add_argument("--long", action="store_true", help="One row per vote type instead of wide columns")
    ap.add_argument("--out", type=Path, default=OUT_DIR, help="Output directory")
    ap.add_argument("--keep-raw", action="store_true", help="Save the downloaded .xlsx alongside the CSVs")
    args = ap.parse_args(argv)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.file:
        source = args.file
    else:
        print(f"Downloading {args.url}", file=sys.stderr)
        data = fetch(args.url)
        if args.keep_raw:
            raw_path = args.out / f"raw_{stamp}.xlsx"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(data)
        source = io.BytesIO(data)

    wb = load_workbook(source, read_only=True, data_only=True)

    jobs = [("summary", SUMMARY_GROUP_SHEET, False)]
    if args.precincts:
        jobs.append(("precincts", PRECINCT_GROUP_SHEET, True))

    for label, sheet, precinct in jobs:
        print(f"Parsing {sheet!r}...", file=sys.stderr)
        records = parse(wb, sheet, precinct)
        if args.long:
            fields, rows = list(records[0].keys()), records
        else:
            fields, rows = to_wide(records)

        if label == "summary" and not args.long:
            problems = check_against_totals(wb, rows)
            if problems:
                print(f"WARNING: {len(problems)} total mismatches:", file=sys.stderr)
                for p in problems[:10]:
                    print("  " + p, file=sys.stderr)
            else:
                print("Vote-type sums match official totals.", file=sys.stderr)

        fmt = "long" if args.long else "wide"
        for name in (f"{label}_{fmt}_{stamp}.csv", f"{label}_{fmt}_latest.csv"):
            write_csv(args.out / name, fields, rows)
        print(f"Wrote {len(rows):,} rows -> {args.out / f'{label}_{fmt}_latest.csv'}", file=sys.stderr)

    wb.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
