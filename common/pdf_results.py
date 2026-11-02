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

SENATE = re.compile(r"^(for\s+)?(u\.?\s*s\.?|united\s+states)\s+senat", re.I)
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


def parse_ess_summary(text: str) -> tuple[str, list[dict], list[str]]:
    """ES&S summary with TOTAL and VOTE % before the groups, e.g. Allen's
    Nov 2025 unofficial report:
        TOTAL VOTE % Election Day AbsenteeProvisional
        Rep Barbara J. Mesker 353 86.73% 302 51 0
    Group columns are taken from the header and must be among KNOWN."""
    known = ["Election Day", "Absentee", "Provisional"]
    lines = [l.strip() for l in text.splitlines()]
    start = next((i for i, l in enumerate(lines) if SENATE.match(l)), None)
    if start is None:
        raise RuntimeError("No U.S. Senate race in the report")
    race = lines[start]
    header = " ".join(lines[start + 1:start + 7])
    if not ("TOTAL" in header and "VOTE %" in header):
        raise RuntimeError(f"ES&S header changed: {header!r}")
    cols = [c for c in known if all(w in header for w in c.split())]
    if cols != known:
        raise RuntimeError(f"ES&S group columns changed (found {cols}): {header!r}")
    row_re = re.compile(rf"^(.+?)\s+({NUM})\s+[\d.]+%\s+" + r"\s+".join([f"({NUM})"] * len(cols)) + "$")
    rows = []
    for l in lines[start + 1:]:
        if "Total Votes Cast" in l or "Precincts Reporting" in l or SENATE.match(l) and l != race:
            break
        m = row_re.match(l)
        if not m:
            continue
        name = re.sub(r"^(Dem|Rep|Lib|Grn|Oth|Non|Ind)\s+", "", m.group(1))
        if name in ("Overvotes", "Undervotes", "Not Assigned"):
            continue
        vals = [_n(v) for v in m.groups()[1:]]
        rows.append({"race": race, "contestant": _name(name), "total": vals[0], **dict(zip(cols, vals[1:]))})
    return race, rows, cols


def parse_positional(data: bytes, race_re: re.Pattern = SENATE) -> tuple[str, list[dict], list[str]]:
    """Layout-aware parser for ES&S / Electionware tables, using word
    POSITIONS on the page instead of extracted text order.

    Why: these reports print multi-line column headers ("Absentee" over
    "Mail"), and plain text extraction emits those words in an order that
    differs between counties using the same software. Here every header word
    is clustered with the words stacked above/below it, which gives a column
    label and its x-range. Each number in a candidate row then goes to the
    header column it sits under. Returns (race, rows, method_columns); TOTAL
    and VOTE % columns are used for the total and dropped from the method list.
    """
    import pdfplumber
    num_re = re.compile(r"^\d[\d,]*$")
    stop = re.compile(r"^(Total Votes Cast|Overvotes|Undervotes|Precincts Reporting|Contest Totals|Vote For)", re.I)
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, x_tolerance=1.5, y_tolerance=2)
            # group words into lines by vertical position
            lines: list[list[dict]] = []
            for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
                if lines and abs(lines[-1][0]["top"] - w["top"]) <= 2.5:
                    lines[-1].append(w)
                else:
                    lines.append([w])
            texts = [" ".join(x["text"] for x in sorted(l, key=lambda w: w["x0"])) for l in lines]
            start = next((i for i, t in enumerate(texts) if race_re.match(t.strip())), None)
            if start is None:
                continue
            race = texts[start].strip()
            # header zone: lines after the title up to the first line that has a name followed by numbers
            first_row = None
            for i in range(start + 1, min(start + 12, len(lines))):
                toks = sorted(lines[i], key=lambda w: w["x0"])
                nums = [w for w in toks if num_re.match(w["text"])]
                if nums and not num_re.match(toks[0]["text"]) and not stop.match(texts[i]):
                    first_row = i
                    break
            if first_row is None:
                raise RuntimeError(f"No candidate rows under {race!r}")
            hdr_words = []
            for w in (w for l in lines[start + 1:first_row] for w in l):
                if re.match(r"^(Vote|For|\d+|Not|More|Than)$", w["text"], re.I) or stop.match(w["text"]):
                    continue
                # Some PDFs glue adjacent header words ("AbsenteeProvisional",
                # "DayTOTAL"). Split at lower->upper case boundaries and share
                # the word's width in proportion to the parts' lengths.
                parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|%|[^A-Za-z%\s]+", w["text"])
                if len(parts) > 1 and "".join(parts) == w["text"]:
                    x, width = w["x0"], w["x1"] - w["x0"]
                    for p in parts:
                        pw = width * len(p) / len(w["text"])
                        hdr_words.append({**w, "text": p, "x0": x, "x1": x + pw})
                        x += pw
                else:
                    hdr_words.append(w)
            # cluster header words into columns by horizontal overlap
            cols: list[dict] = []
            for w in sorted(hdr_words, key=lambda w: w["x0"]):
                for c in cols:
                    # real overlap (stacked words), not just touching edges
                    if min(w["x1"], c["x1"]) - max(w["x0"], c["x0"]) > 1.0:
                        c["words"].append(w)
                        c["x0"], c["x1"] = min(c["x0"], w["x0"]), max(c["x1"], w["x1"])
                        break
                else:
                    cols.append({"x0": w["x0"], "x1": w["x1"], "words": [w]})
            for c in cols:
                c["label"] = " ".join(x["text"] for x in sorted(c["words"], key=lambda w: (w["top"], w["x0"])))
                c["label"] = re.sub(r"\s+", " ", c["label"]).replace("Provision al", "Provisional").strip()
                c["xc"] = (c["x0"] + c["x1"]) / 2
            labels = [c["label"] for c in cols]
            if not any(l.upper() == "TOTAL" for l in labels):
                raise RuntimeError(f"No TOTAL column under {race!r}: {labels}")
            rows = []
            for i in range(first_row, len(lines)):
                t = texts[i].strip()
                if stop.match(t) or race_re.match(t) and i != start:
                    break
                toks = sorted(lines[i], key=lambda w: w["x0"])
                nums = [w for w in toks if num_re.match(w["text"])]
                if not nums:
                    if rows:
                        break
                    continue
                name = " ".join(w["text"] for w in toks if w["x1"] <= nums[0]["x0"] and not w["text"].endswith("%"))
                name = re.sub(r"^(Dem|Rep|Lib|Grn|Opc|Oth|Non|Ind|DEM|REP|LIB|GRN|OPC|OTH|NON|IND|OTHER)\s+", "", name).strip()
                if name in ("Not Assigned",) or not name:
                    continue
                vals = {}
                for n in nums:
                    xc = (n["x0"] + n["x1"]) / 2
                    c = min(cols, key=lambda c: abs(c["xc"] - xc) if not (c["x0"] - 2 <= xc <= c["x1"] + 2) else -1)
                    if c["label"] in vals:
                        raise RuntimeError(f"Two numbers under {c['label']!r} in row {t!r}")
                    vals[c["label"]] = _n(n["text"])
                total_label = next(l for l in labels if l.upper() == "TOTAL")
                method_cols = [l for l in labels if l.upper() not in ("TOTAL", "VOTE %", "VOTE", "%")]
                rows.append({"race": race, "contestant": _name(name), "total": vals.get(total_label, 0),
                             **{m: vals.get(m, 0) for m in method_cols}})
            if re.match(r"write-?in:", " ".join(r["contestant"] for r in rows), re.I):
                pass
            # Fold individually listed write-ins ("Write-In: a. Stephen Faris") into Write-in.
            merged: dict[str, dict] = {}
            for r in rows:
                key = "Write-in" if re.match(r"write-?in", r["contestant"], re.I) else r["contestant"]
                if key == "Write-in" and re.match(r"write-?in\s*:", r["contestant"], re.I) and "Write-in" in merged \
                        and merged["Write-in"].get("_from_totals"):
                    continue  # "Write-In Totals" already counts the named ones
                if key in merged:
                    for k, v in r.items():
                        if isinstance(v, int):
                            merged[key][k] += v
                else:
                    merged[key] = {**r, "contestant": key,
                                   "_from_totals": bool(re.match(r"write-?in totals", r["contestant"], re.I))}
            out = []
            for r in merged.values():
                r.pop("_from_totals", None)
                out.append(r)
            return race, out, [l for l in labels if l.upper() not in ("TOTAL", "VOTE %", "VOTE", "%")]
    raise RuntimeError("No U.S. Senate race in the report")


PARSERS = {"electionware": parse_electionware, "dominion": parse_dominion, "ess_summary": parse_ess_summary}


def run(county: str, layout: str, data: bytes, out_dir: Path, source_url: str) -> int:
    if layout == "positional":
        race, rows, cols = parse_positional(data)
        if not cols:
            raise SystemExit(f"{county}: the Senate block has no vote-method columns (TOTAL only)")
    else:
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
