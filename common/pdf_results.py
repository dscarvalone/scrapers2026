"""U.S. Senate results by vote method from county election-night PDF reports.

Only the U.S. Senate race is extracted (that's all common/senate.py needs).
Each layout parser checks that the report's column headers are exactly what
was verified, and raises otherwise, so a changed report fails loudly instead
of producing misassigned columns.

Layouts (verified 2026-11-01):

  electionware   ES&S Electionware "Summary Report", e.g. Licking.
                 Per-candidate line: Name TOTAL ElectionDay AbsenteeOffice AbsenteeMail Provisional
                 Order confirmed on Licking's May 2026 report, where the
                 four groups sum to TOTAL (e.g. 9,212 = 6,495 + 975 + 1,699 + 43).
  dominion       Dominion "Zero Report"/results, e.g. Miami.
                 Header: Choice | Votes | Vote % | AB | ED | EV | PR
                 Per candidate, one value per line: name, votes, pct, AB, ED, EV, PR.
                 Order taken from the printed header; not yet confirmed on a
                 report with real votes (Miami's May 2026 PDF has no text layer).

Output: output/summary_wide_latest.csv, same shape as the other scrapers.
"""

from __future__ import annotations

import csv
import io
import re
import sys
from datetime import datetime
from pathlib import Path

SENATE = re.compile(r"^(u\.?\s*s\.?|united\s+states)\s+senat", re.I)
NUM = r"[\d,]+"
TAIL = ["total", "precincts_reported", "precincts_total", "generated_at", "source_format"]


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    if data[:4] != b"%PDF":
        raise RuntimeError(f"Not a PDF (starts {data[:20]!r})")
    text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    if len(text.strip()) < 200:
        raise RuntimeError("PDF has no usable text layer (scanned?)")
    return text


def _n(s: str) -> int:
    return int(s.replace(",", ""))


def _name(raw: str) -> str:
    raw = " ".join(raw.split())
    return "Write-in" if re.fullmatch(r"write-?in( totals)?", raw, re.I) else raw


def parse_electionware(text: str) -> tuple[str, list[dict], list[str]]:
    lines = [l.strip() for l in text.splitlines()]
    start = next((i for i, l in enumerate(lines) if SENATE.match(l)), None)
    if start is None:
        raise RuntimeError("No U.S. Senate race in the report")
    race = lines[start]
    header = " ".join(lines[start + 1:start + 9])
    for want in ("Election Day", "Absentee Office", "Absentee Mail", "Provisional", "TOTAL"):
        # header words are split across lines in the extracted text
        if not all(w in header for w in want.split()):
            raise RuntimeError(f"Electionware header changed; missing {want!r}: {header!r}")
    cols = ["Election Day", "Absentee Office", "Absentee Mail", "Provisional"]
    row_re = re.compile(rf"^(.+?)\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})$")
    rows = []
    for l in lines[start + 1:]:
        # With real votes the line comes out as "100.00%Total Votes Cast ..."
        if "Total Votes Cast" in l:
            break
        m = row_re.match(l)
        if not m or m.group(1) in ("Overvotes", "Undervotes", "Not Assigned"):
            continue
        vals = [_n(v) for v in m.groups()[1:]]
        rows.append({"race": race, "contestant": _name(m.group(1)), "total": vals[0],
                     **dict(zip(cols, vals[1:]))})
    return race, rows, cols


def parse_dominion(text: str) -> tuple[str, list[dict], list[str]]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    start = next((i for i, l in enumerate(lines) if SENATE.match(l)), None)
    if start is None:
        raise RuntimeError("No U.S. Senate race in the report")
    race = re.sub(r"\s*\(Vote for \d+\)\s*$", "", lines[start])
    hdr_zone = lines[max(0, start - 12):start]
    if not all(h in hdr_zone for h in ("AB", "ED", "EV", "PR")) or "Votes" not in hdr_zone:
        raise RuntimeError(f"Dominion header changed near the Senate race: {hdr_zone!r}")
    cols = ["AB", "ED", "EV", "PR"]
    i = start + 1
    if "ballots" in lines[i] and "registered voters" in lines[i]:
        i += 1
    rows = []
    while i + 6 < len(lines):
        name = lines[i]
        if name in ("Total", "Overvotes", "Undervotes") or SENATE.match(name):
            break
        vals = lines[i + 1:i + 7]
        if not (re.fullmatch(NUM, vals[0]) and vals[1].endswith("%") and all(re.fullmatch(NUM, v) for v in vals[2:])):
            raise RuntimeError(f"Unexpected Dominion row for {name!r}: {vals!r}")
        rows.append({"race": race, "contestant": _name(name), "total": _n(vals[0]),
                     **dict(zip(cols, (_n(v) for v in vals[2:])))})
        i += 7
    return race, rows, cols


PARSERS = {"electionware": parse_electionware, "dominion": parse_dominion}


def run(county: str, layout: str, data: bytes, out_dir: Path, source_url: str) -> int:
    race, rows, cols = PARSERS[layout](pdf_text(data))
    if not rows:
        raise SystemExit(f"{county}: found {race!r} but no candidate rows")
    gen = datetime.now().astimezone().isoformat(timespec="seconds")  # PDFs carry no reliable timestamp
    for r in rows:
        r.update(precincts_reported="", precincts_total="", generated_at=gen, source_format=f"pdf_{layout}")
    bad = [f"{r['contestant']}: {sum(r[c] for c in cols)} vs {r['total']}" for r in rows
           if sum(r[c] for c in cols) != r["total"]]
    print(f"{county}: {layout} PDF, {race!r}, {len(rows)} candidates ({source_url})", file=sys.stderr)
    print(("WARNING: vote types don't sum to total: " + "; ".join(bad)) if bad else "Vote-type sums match totals.",
          file=sys.stderr)
    fields = ["race", "contestant", *cols, *TAIL]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in (f"summary_wide_{stamp}.csv", "summary_wide_latest.csv"):
        with (out_dir / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {out_dir / 'summary_wide_latest.csv'}", file=sys.stderr)
    return 1 if bad else 0
