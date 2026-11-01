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
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Fields common to both formats. Vote-type columns are inserted after
# "withdrawn" and vary by source (detected per feed; see XML_VOTE_LABELS).
BASE_FIELDS = [
    "race_id", "race", "vote_for", "contestant_id", "contestant", "party",
    "write_in", "withdrawn",
]
TAIL_FIELDS = [
    "total", "pct", "winner",
    "race_total_votes", "ballots_cast", "over_votes", "under_votes", "blank_voted",
    "precincts_reported", "precincts_total", "generated_at", "source_format",
]

# Vote-method columns differ between ENR installs, so they are detected from
# the feed itself: any XML tag / CSV column ending in "Votes" that isn't a
# total or an over/under count. Known names get a stable label; anything new
# gets a label derived from its name (and passes through common/senate.py
# unmapped until someone adds it to METHOD_MAP).
#
#   Warren/Butler sample XML: ElectionDayVotes, EarlyVotingVotes,
#                             MailBallotsVotes, ProvisionalVotes
#   Franklin XML (live, 2026): EarlyVotingVotes, AbsenteeBallotsVotes,
#                             ElectionDayVotes, ProvisionalVotingVotes
XML_VOTE_LABELS = {
    "ElectionDayVotes": "Election Day",
    "EarlyVotingVotes": "Early Voting",
    "MailBallotsVotes": "Mail Ballots",
    "AbsenteeBallotsVotes": "Absentee Ballots",
    "AbsenteeVotingVotes": "Absentee Voting",   # SOS ENR, e.g. Butler (live, 2026)
    # Stark's install doubles the suffix (labels seen in discovery:
    # "Early In Person Votes", "Voteby Mail Votes").
    "EarlyInPersonVotesVotes": "Early In Person",
    "VotebyMailVotesVotes": "Vote by Mail",
    # Summit's install (live, 2026): absentee split into walk-in and mail,
    # plus "timely" absentee, which is left as its own column (meaning
    # unconfirmed; see REPORT.md).
    "PollsVotes": "Election Day",
    "ABSWalkinVotes": "Absentee Walk-in",
    "ABSMailVotes": "Absentee Mail",
    "TimelyABSVotes": "Timely Absentee",
    "ProvisionalVotes": "Provisional",
    "ProvisionalVotingVotes": "Provisional",
}
CSV_VOTE_LABELS = {
    "Election Day Votes": "Election Day",
    "Early Voting Votes": "Early Voting",
    "Absentee Voting Votes": "Absentee",
    "Absentee Ballots Votes": "Absentee Ballots",
    "Mail Ballots Votes": "Mail Ballots",
    "Provisional Voting Votes": "Provisional",
    "Provisional Votes": "Provisional",
}
# MinimumVotes is a race setting (Franklin), not a vote count.
NOT_METHODS_XML = {"Votes", "TotalVotes", "OverVotes", "UnderVotes", "MinimumVotes"}
NOT_METHODS_CSV = {"Total Votes", "Over Votes", "Under Votes"}


def _label_from_tag(tag: str) -> str:
    # "AbsenteeBallotsVotes" -> "Absentee Ballots"
    return " ".join(re.findall(r"[A-Z][a-z]*", tag[: -len("Votes")])) or tag


def fields_for(vote_types: list[str]) -> list[str]:
    return BASE_FIELDS + vote_types + TAIL_FIELDS


# ---------------------------------------------------------------- fetching

def fetch(url: str) -> bytes:
    # The site appends ?v=<epoch ms> to dodge caches; do the same.
    sep = "&" if "?" in url else "?"
    if "liveresults.boe.ohio.gov" in url:
        # SOS-hosted ENR blocks plain HTTP; go through the owner's Chrome
        # window (see common/sos_browser.py).
        from common import sos_browser
        data = sos_browser.fetch_bytes(f"{url}{sep}v={int(time.time() * 1000)}")
        detect(data)
        return data
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


# Election-day votes are <ElectionDayVotes> in most installs, <PollsVotes> in
# Summit's. One of them has to be present.
REQUIRED_XML_TAGS = {"RaceName", "ContestantName"}
ELECTION_DAY_TAGS = {"ElectionDayVotes", "PollsVotes"}


def _xml_vote_tags(tags: list[str]) -> list[tuple[str, str]]:
    return [
        (t, XML_VOTE_LABELS.get(t) or _label_from_tag(t))
        for t in tags if t.endswith("Votes") and t not in NOT_METHODS_XML
    ]


def parse_xml(data: bytes):
    root = ET.fromstring(data)
    tables = root.findall("Table")
    vote_tags: list[tuple[str, str]] = []
    if tables:
        present = [child.tag for child in tables[0]]
        missing = REQUIRED_XML_TAGS - set(present)
        if not ELECTION_DAY_TAGS & set(present):
            missing |= {"ElectionDayVotes|PollsVotes"}
        vote_tags = _xml_vote_tags(present)
        if missing or len(vote_tags) < 2 or not ({"Votes", "TotalVotes"} & set(present)):
            raise RuntimeError(
                f"XML is missing expected fields {sorted(missing) or '(vote/total tags)'}; "
                f"it has {sorted(present)}"
            )
        unknown = [t for t, _ in vote_tags if t not in XML_VOTE_LABELS]
        if unknown:
            print(f"NOTE: unrecognized vote-type tags {unknown}; labels derived from tag names",
                  file=sys.stderr)
    t_ = lambda el, tag: (el.findtext(tag) or "").strip()
    meta = {
        "generated_at": t_(root, "GeneratedDate"),
        "registered_voters": _int(root.findtext("RegisteredVoters")),
        "total_ballots_cast": _int(root.findtext("TotalBallotsCast")),
    }
    rows = []
    for t in tables:
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
        method_sum = 0
        for tag, label in vote_tags:
            row[label] = _int(t.findtext(tag))
            method_sum += row[label]
        # Installs disagree on which tag is the candidate's total: in the
        # Warren/Butler samples it's <Votes> (and <TotalVotes> is the race
        # total); in Franklin's live feed <Votes> is always 0 and
        # <TotalVotes> is the candidate total. Use whichever matches the
        # method sum; if neither does, keep <Votes> (when present) so
        # check() reports the mismatch.
        votes, total_votes = _int(t.findtext("Votes")), _int(t.findtext("TotalVotes"))
        if t.find("Votes") is not None and (votes == method_sum or t.find("TotalVotes") is None):
            total = votes
        elif total_votes == method_sum:
            total = total_votes
        else:
            total = votes if t.find("Votes") is not None else total_votes
        row.update({
            "total": total,
            "pct": float(t_(t, "ContestantVotePercent").rstrip("%") or 0),
            "winner": t_(t, "ContestantWinner") == "Y",
            "race_total_votes": None,  # filled below from candidate totals
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
    _fill_race_totals(rows)
    return meta, rows, _unique([label for _, label in vote_tags])


def _unique(labels: list[str]) -> list[str]:
    if len(set(labels)) != len(labels):
        raise RuntimeError(f"Two vote-type columns map to the same label: {labels}")
    return labels


def _fill_race_totals(rows: list[dict]) -> None:
    race_totals: dict[str, int] = {}
    for row in rows:
        race_totals[row["race"]] = race_totals.get(row["race"], 0) + row["total"]
    for row in rows:
        row["race_total_votes"] = race_totals[row["race"]]


# ---------------------------------------------------------------- CSV

def parse_csv(data: bytes):
    """CSV has a two-line preamble ("UNOFFICIAL ELECTION RESULTS", county name),
    a header, a "Total Precincts Reported" line, then one row per choice.
    It has no party, IDs, percentages or timestamp."""
    lines = data.decode("utf-8-sig").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("Contest Name"))
    reader = csv.reader(lines[start:])
    header = [h.strip() for h in next(reader)]
    vote_cols = [
        (h, CSV_VOTE_LABELS.get(h) or h[: -len(" Votes")])
        for h in header if h.endswith(" Votes") and h not in NOT_METHODS_CSV
    ]
    if len(vote_cols) < 2 or "Total Votes" not in header:
        raise RuntimeError(f"CSV is missing expected vote columns; header is {header}")
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
            "vote_for": _int(r.get("Vote For", "")),
            "contestant_id": "",
            "contestant": contestant,
            "party": r.get("Party", ""),
            "write_in": contestant.lower() == "write-in",
            "withdrawn": "",
        }
        for col, label in vote_cols:
            row[label] = _int(r[col])
        row.update({
            "total": _int(r["Total Votes"]),
            "pct": None,  # filled below
            "winner": "",
            "race_total_votes": None,  # filled below
            "ballots_cast": _int(r.get("Ballots Cast", "")),
            "over_votes": _int(r.get("Over Votes", "")),
            "under_votes": _int(r.get("Under Votes", "")),
            "blank_voted": "",
            "precincts_reported": _int(r.get("Precincts Reported", "")),
            "precincts_total": _int(r.get("Number Of Precincts", "")),
            "generated_at": "",
            "source_format": "csv",
        })
        rows.append(row)
    # CSV has no percentages: compute share of the race's candidate votes.
    _fill_race_totals(rows)
    for row in rows:
        rt = row["race_total_votes"]
        row["pct"] = round(100 * row["total"] / rt, 2) if rt else 0.0
    return meta, rows, _unique([label for _, label in vote_cols])


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


def run(county: str, urls: list[str] | str, out_dir: Path, argv=None,
        expect_year: str | None = None) -> int:
    """expect_year: if set, fail when the feed's GeneratedDate is from another
    year (catches a stale election ID). Only XML carries a timestamp."""
    urls = [urls] if isinstance(urls, str) else list(urls)
    ap = argparse.ArgumentParser(description=f"{county} County, OH results by vote type (Ohio ENR feed)")
    ap.add_argument("--url", action="append", help="Summary XML/CSV URL (repeatable; tried in order)")
    ap.add_argument("--file", help="Parse a local XML or CSV file instead of downloading")
    ap.add_argument("--long", action="store_true", help="One row per vote type instead of wide columns")
    ap.add_argument("--out", type=Path, default=out_dir, help="Output directory")
    args = ap.parse_args(argv)

    if args.file:
        meta, rows, vote_types = parse(Path(args.file).read_bytes())
    else:
        # Try each source in order; a download error or a file in an
        # unexpected shape both fall through to the next one.
        parsed, errors = None, []
        for url in args.url or urls:
            print(f"Downloading {url}", file=sys.stderr)
            try:
                parsed = parse(fetch(url))
                break
            except Exception as e:
                errors.append(f"{url}: {e}")
                print(f"  failed: {e}", file=sys.stderr)
        if parsed is None:
            raise SystemExit(f"{county}: all sources failed:\n  " + "\n  ".join(errors))
        meta, rows, vote_types = parsed
    gen = meta.get("generated_at") or ""
    if expect_year and gen and not gen.startswith(expect_year):
        raise SystemExit(f"{county}: feed generated {gen}, expected {expect_year}; "
                         "the election ID is probably stale")
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
