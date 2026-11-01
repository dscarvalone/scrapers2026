"""Parser for Ohio's shared election-night results feed (liveresults.boe.ohio.gov/ENR).

Counties on this system publish a summary XML at a URL like
    https://liveresults.boe.ohio.gov/ENR/<county>ohenr/<election_id>/summary_<election_id>.xml
with one <Table> per race/contestant and vote counts split by vote type.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# XML field -> output column, in output order.
VOTE_TYPES = [
    ("ElectionDayVotes", "Election Day"),
    ("EarlyVotingVotes", "Early Voting"),
    ("MailBallotsVotes", "Mail Ballots"),
    ("ProvisionalVotes", "Provisional"),
]

FIELDS = [
    "race_id", "race", "vote_for", "contestant_id", "contestant", "party",
    "write_in", "withdrawn",
    *[label for _, label in VOTE_TYPES],
    "total", "pct", "winner",
    "race_total_votes", "over_votes", "under_votes", "blank_voted",
    "precincts_reported", "precincts_total", "generated_at",
]


def fetch(url: str) -> bytes:
    # The site appends ?v=<epoch ms> to dodge caches; do the same.
    sep = "&" if "?" in url else "?"
    resp = requests.get(
        f"{url}{sep}v={int(time.time() * 1000)}",
        timeout=60,
        headers={"User-Agent": "scrapers2026 (election results research)"},
    )
    resp.raise_for_status()
    if b"<NewDataSet" not in resp.content[:500]:
        raise RuntimeError(f"Response from {url} doesn't look like an ENR summary XML.")
    return resp.content


def _int(el, tag) -> int:
    text = (el.findtext(tag) or "").strip().replace(",", "")
    return int(text) if text else 0


def _txt(el, tag) -> str:
    return (el.findtext(tag) or "").strip()


def parse(xml_bytes: bytes) -> tuple[dict, list[dict]]:
    root = ET.fromstring(xml_bytes)
    meta = {
        "generated_at": _txt(root, "GeneratedDate"),
        "registered_voters": _int(root, "RegisteredVoters"),
        "total_ballots_cast": _int(root, "TotalBallotsCast"),
        "turnout": _txt(root, "VoterTurnout"),
    }
    rows = []
    for t in root.findall("Table"):
        row = {
            "race_id": _txt(t, "RaceID"),
            "race": _txt(t, "RaceName"),
            "vote_for": _int(t, "VoteFor"),
            "contestant_id": _txt(t, "ContestantID"),
            "contestant": _txt(t, "ContestantName"),
            "party": _txt(t, "Party"),
            "write_in": _txt(t, "ContestantWriteIn") == "Y",
            "withdrawn": _txt(t, "ContestantWithdrawn") == "Y",
        }
        for tag, label in VOTE_TYPES:
            row[label] = _int(t, tag)
        row.update({
            "total": _int(t, "Votes"),
            "pct": float(_txt(t, "ContestantVotePercent").rstrip("%") or 0),
            "winner": _txt(t, "ContestantWinner") == "Y",
            "race_total_votes": _int(t, "TotalVotes"),
            "over_votes": _int(t, "OverVotes"),
            "under_votes": _int(t, "UnderVotes"),
            "blank_voted": _int(t, "BlankVoted"),
            "precincts_reported": _int(t, "PrecReported"),
            "precincts_total": _int(t, "NumberOfPrec"),
            "generated_at": meta["generated_at"],
        })
        rows.append(row)
    return meta, rows


def check(rows: list[dict]) -> list[str]:
    """Vote types should add up to each contestant's total."""
    problems = []
    for r in rows:
        s = sum(r[label] for _, label in VOTE_TYPES)
        if s != r["total"]:
            problems.append(f"{r['race']} / {r['contestant']}: vote types sum to {s}, total is {r['total']}")
    return problems


def to_long(rows: list[dict]) -> tuple[list[str], list[dict]]:
    keep = [f for f in FIELDS if f not in {label for _, label in VOTE_TYPES}]
    out = []
    for r in rows:
        for _, label in VOTE_TYPES:
            out.append({**{k: r[k] for k in keep}, "vote_type": label, "votes": r[label]})
    return keep + ["vote_type", "votes"], out


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def run(county: str, default_url: str, out_dir: Path, argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"{county} County, OH results by vote type (Ohio ENR feed)")
    ap.add_argument("--url", default=default_url, help="summary XML URL")
    ap.add_argument("--file", help="Parse a local XML file instead of downloading")
    ap.add_argument("--long", action="store_true", help="One row per vote type instead of wide columns")
    ap.add_argument("--out", type=Path, default=out_dir, help="Output directory")
    args = ap.parse_args(argv)

    if args.file:
        data = Path(args.file).read_bytes()
    else:
        print(f"Downloading {args.url}", file=sys.stderr)
        data = fetch(args.url)

    meta, rows = parse(data)
    print(
        f"{county}: {len(rows)} rows, {len({r['race_id'] for r in rows})} races, "
        f"generated {meta['generated_at']}, ballots cast {meta['total_ballots_cast']:,}",
        file=sys.stderr,
    )
    problems = check(rows)
    if problems:
        print(f"WARNING: {len(problems)} rows where vote types don't sum to the total:", file=sys.stderr)
        for p in problems[:10]:
            print("  " + p, file=sys.stderr)
    else:
        print("Vote-type sums match totals.", file=sys.stderr)

    fmt = "long" if args.long else "wide"
    fields, out_rows = to_long(rows) if args.long else (FIELDS, rows)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for name in (f"summary_{fmt}_{stamp}.csv", f"summary_{fmt}_latest.csv"):
        write_csv(args.out / name, fields, out_rows)
    print(f"Wrote {len(out_rows):,} rows -> {args.out / f'summary_{fmt}_latest.csv'}", file=sys.stderr)
    return 0
