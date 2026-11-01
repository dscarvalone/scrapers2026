"""Parser for Ohio's shared election-night results feed (liveresults.boe.ohio.gov/ENR).

Counties on this system publish results under
    https://liveresults.boe.ohio.gov/ENR/<county>ohenr/<election_id>/
as a summary XML (summary_<id>.xml) and/or a summary CSV (summary_<id>.csv).
Both are handled; the XML is richer (party, IDs, timestamp, and sometimes a
finer vote-type split), so counties should list it first.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Fields common to both formats. Vote-type columns are inserted after
# "withdrawn" and vary by source (see XML_VOTE_TYPES / CSV_VOTE_TYPES).
BASE_FIELDS = [
    "race_id", "race", "vote_for", "contestant_id", "contestant", "party",
    "write_in", "withdrawn",
]
TAIL_FIELDS = [
    "total", "pct", "winner",
    "race_total_votes", "ballots_cast", "over_votes", "under_votes", "blank_voted",
    "precincts_reported", "precincts_total", "generated_at", "source_format",
]

XML_VOTE_TYPES = [
    ("ElectionDayVotes", "Election Day"),
    ("EarlyVotingVotes", "Early Voting"),
    ("MailBallotsVotes", "Mail Ballots"),
    ("ProvisionalVotes", "Provisional"),
]
CSV_VOTE_TYPES = [
    ("Election Day Votes", "Election Day"),
    ("Absentee Voting Votes", "Absentee"),
    ("Provisional Voting Votes", "Provisional"),
]


def fields_for(vote_types: list[str]) -> list[str]:
    return BASE_FIELDS + vote_types + TAIL_FIELDS


# ---------------------------------------------------------------- fetching

def fetch(url: str) -> bytes:
    # The site appends ?v=<epoch ms> to dodge caches; do the same.
    sep = "&" if "?" in url else "?"
    resp = requests.get(
        f"{url}{sep}v={int(time.time() * 1000)}",
        timeout=60,
        headers={"User-Agent": "scrapers2026 (election results research)"},
    )
    resp.raise_for_status()
    detect(resp.content)  # raises if it isn't an ENR summary
    return resp.content


def detect(data: bytes) -> str:
    head = data[:600].lstrip(b"\xef\xbb\xbf").lstrip()
    if b"<NewDataSet" in head:
        return "xml"
    if b"Contest Name" in head and b"Candidate Name" in head:
        return "csv"
    raise RuntimeError("Not an ENR summary XML or CSV (got: %r...)" % head[:80])


# ---------------------------------------------------------------- XML

def _int(text) -> int:
    text = (text or "").strip().replace(",", "")
    return int(text) if text else 0


def parse_xml(data: bytes):
    root = ET.fromstring(data)
    t_ = lambda el, tag: (el.findtext(tag) or "").strip()
    meta = {
        "generated_at": t_(root, "GeneratedDate"),
        "registered_voters": _int(root.findtext("RegisteredVoters")),
        "total_ballots_cast": _int(root.findtext("TotalBallotsCast")),
    }
    rows = []
    for t in root.findall("Table"):
        row = {
            "race_id": t_(t, "RaceID"),
            "race": t_(t, "RaceName"),
            "vote_for": _int(t.findtext("VoteFor")),
            "contestant_id": t_(t, "ContestantID"),
            "contestant": t_(t, "ContestantName"),
            "party": t_(t, "Party"),
            "write_in": t_(t, "ContestantWriteIn") == "Y",
            "withdrawn": t_(t, "ContestantWithdrawn") == "Y",
        }
        for tag, label in XML_VOTE_TYPES:
            row[label] = _int(t.findtext(tag))
        row.update({
            "total": _int(t.findtext("Votes")),
            "pct": float(t_(t, "ContestantVotePercent").rstrip("%") or 0),
            "winner": t_(t, "ContestantWinner") == "Y",
            "race_total_votes": _int(t.findtext("TotalVotes")),
            "ballots_cast": "",
            "over_votes": _int(t.findtext("OverVotes")),
            "under_votes": _int(t.findtext("UnderVotes")),
            "blank_voted": _int(t.findtext("BlankVoted")),
            "precincts_reported": _int(t.findtext("PrecReported")),
            "precincts_total": _int(t.findtext("NumberOfPrec")),
            "generated_at": meta["generated_at"],
            "source_format": "xml",
        })
        rows.append(row)
    return meta, rows, [label for _, label in XML_VOTE_TYPES]


# ---------------------------------------------------------------- CSV

def parse_csv(data: bytes):
    """CSV has a two-line preamble ("UNOFFICIAL ELECTION RESULTS", county name),
    a header, a "Total Precincts Reported" line, then one row per choice.
    It has no party, IDs, percentages or timestamp."""
    lines = data.decode("utf-8-sig").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("Contest Name"))
    reader = csv.reader(lines[start:])
    header = [h.strip() for h in next(reader)]
    meta = {"generated_at": "", "precincts_reported_overall": None}
    rows = []
    for rec in reader:
        if not rec or all(not c.strip() for c in rec):
            continue
        if rec[0].strip() == "Total Precincts Reported":
            meta["precincts_reported_overall"] = _int(rec[1] if len(rec) > 1 else "")
            continue
        if len(rec) != len(header):
            raise RuntimeError(f"Unexpected CSV row ({len(rec)} fields): {rec}")
        r = dict(zip(header, (c.strip() for c in rec)))
        contestant = " ".join(r["Candidate Name"].split())
        row = {
            "race_id": "",
            "race": " ".join(r["Contest Name"].split()),
            "vote_for": _int(r["Vote For"]),
            "contestant_id": "",
            "contestant": contestant,
            "party": r["Party"],
            "write_in": contestant.lower() == "write-in",
            "withdrawn": "",
        }
        for col, label in CSV_VOTE_TYPES:
            row[label] = _int(r[col])
        row.update({
            "total": _int(r["Total Votes"]),
            "pct": None,  # filled below
            "winner": "",
            "race_total_votes": None,  # filled below
            "ballots_cast": _int(r["Ballots Cast"]),
            "over_votes": _int(r["Over Votes"]),
            "under_votes": _int(r["Under Votes"]),
            "blank_voted": "",
            "precincts_reported": _int(r["Precincts Reported"]),
            "precincts_total": _int(r["Number Of Precincts"]),
            "generated_at": "",
            "source_format": "csv",
        })
        rows.append(row)
    # CSV has no percentages: compute share of the race's candidate votes.
    race_totals: dict[str, int] = {}
    for row in rows:
        race_totals[row["race"]] = race_totals.get(row["race"], 0) + row["total"]
    for row in rows:
        rt = race_totals[row["race"]]
        row["race_total_votes"] = rt
        row["pct"] = round(100 * row["total"] / rt, 2) if rt else 0.0
    return meta, rows, [label for _, label in CSV_VOTE_TYPES]


def parse(data: bytes):
    return parse_xml(data) if detect(data) == "xml" else parse_csv(data)


# ---------------------------------------------------------------- output

def check(rows: list[dict], vote_types: list[str]) -> list[str]:
    """Vote types should add up to each contestant's total."""
    problems = []
    for r in rows:
        s = sum(r[vt] for vt in vote_types)
        if s != r["total"]:
            problems.append(f"{r['race']} / {r['contestant']}: vote types sum to {s}, total is {r['total']}")
    return problems


def to_long(rows: list[dict], vote_types: list[str]):
    keep = BASE_FIELDS + TAIL_FIELDS
    out = [
        {**{k: r[k] for k in keep}, "vote_type": vt, "votes": r[vt]}
        for r in rows for vt in vote_types
    ]
    return keep + ["vote_type", "votes"], out


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def run(county: str, urls: list[str] | str, out_dir: Path, argv=None) -> int:
    urls = [urls] if isinstance(urls, str) else list(urls)
    ap = argparse.ArgumentParser(description=f"{county} County, OH results by vote type (Ohio ENR feed)")
    ap.add_argument("--url", action="append", help="Summary XML/CSV URL (repeatable; tried in order)")
    ap.add_argument("--file", help="Parse a local XML or CSV file instead of downloading")
    ap.add_argument("--long", action="store_true", help="One row per vote type instead of wide columns")
    ap.add_argument("--out", type=Path, default=out_dir, help="Output directory")
    args = ap.parse_args(argv)

    if args.file:
        data = Path(args.file).read_bytes()
    else:
        data, errors = None, []
        for url in args.url or urls:
            print(f"Downloading {url}", file=sys.stderr)
            try:
                data = fetch(url)
                break
            except Exception as e:  # try the next source
                errors.append(f"{url}: {e}")
                print(f"  failed: {e}", file=sys.stderr)
        if data is None:
            raise SystemExit(f"{county}: all sources failed:\n  " + "\n  ".join(errors))

    meta, rows, vote_types = parse(data)
    print(
        f"{county}: {rows[0]['source_format'] if rows else '?'} feed, {len(rows)} rows, "
        f"{len({r['race'] for r in rows})} races"
        + (f", generated {meta['generated_at']}" if meta.get("generated_at") else ""),
        file=sys.stderr,
    )
    problems = check(rows, vote_types)
    if problems:
        print(f"WARNING: {len(problems)} rows where vote types don't sum to the total:", file=sys.stderr)
        for p in problems[:10]:
            print("  " + p, file=sys.stderr)
    else:
        print("Vote-type sums match totals.", file=sys.stderr)

    fmt = "long" if args.long else "wide"
    fields, out_rows = to_long(rows, vote_types) if args.long else (fields_for(vote_types), rows)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for name in (f"summary_{fmt}_{stamp}.csv", f"summary_{fmt}_latest.csv"):
        write_csv(args.out / name, fields, out_rows)
    print(f"Wrote {len(out_rows):,} rows -> {args.out / f'summary_{fmt}_latest.csv'}", file=sys.stderr)
    return 0
