"""Parser for Clarity / Scytl election-night results sites (e.g. Hamilton:
results.votehamiltoncountyohio.gov/OH/Hamilton/127473/).

Clarity publishes a version number at <base>/current_ver.txt and, for that
version, a detail export at <base>/<ver>/reports/detailxml.zip. In the
export, each <Contest> has <Choice totalVotes=...> elements with
<VoteType name=... votes=...> children: the per-candidate split by vote
method. Hamilton (Nov 2026) uses two vote types: "Election" and "Early".

Write-in candidates are listed by name with a "(W)" suffix; they are summed
into a single "Write-in" line to match the other county feeds.

Plain HTTP, no Cloudflare check (tested 2026-11-01), so this runs in Actions.
Output: output/summary_wide_latest.csv, same shape as the other scrapers,
one row per race and choice, a column per vote type, and a total.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

import requests

UA = {"User-Agent": "scrapers2026 (election results research)"}
TAIL = ["total", "precincts_reported", "precincts_total", "generated_at", "source_format"]
WRITE_IN = re.compile(r"\(\s*w\s*\)\s*$|^write-?in", re.I)


def fetch(base: str) -> tuple[str, bytes]:
    base = base.rstrip("/")
    ver = requests.get(f"{base}/current_ver.txt", headers=UA, timeout=30).text.strip()
    if not ver.isdigit():
        raise RuntimeError(f"Unexpected current_ver.txt: {ver[:80]!r}")
    time.sleep(1.1)
    r = requests.get(f"{base}/{ver}/reports/detailxml.zip", headers=UA, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
        return ver, z.read(name)


def parse(xml: bytes) -> tuple[dict, list[dict], list[str]]:
    root = ET.fromstring(xml)
    gen = (root.findtext("Timestamp") or "").strip()
    rows, vtypes = [], []
    for c in root.iter("Contest"):
        race = c.get("text", "").strip()
        merged: dict[str, dict] = {}
        for ch in c.findall("Choice"):
            raw = " ".join((ch.get("text") or "").split())
            name = "Write-in" if WRITE_IN.search(raw) else raw
            row = merged.setdefault(name, {
                "race_id": c.get("key", ""), "race": race, "contestant": name,
                "party": ch.get("party", ""), "write_in": name == "Write-in", "total": 0,
                "precincts_reported": c.get("precinctsReported", ""),
                "precincts_total": c.get("precinctsReporting", ""),  # Clarity: "reporting" = participating
                "generated_at": gen, "source_format": "clarity",
                "write_in_detail": "",
            })
            row["total"] += int(ch.get("totalVotes") or 0)
            for vt in ch.findall("VoteType"):
                n = vt.get("name", "").strip()
                if n not in vtypes:
                    vtypes.append(n)
                row[n] = row.get(n, 0) + int(vt.get("votes") or 0)
            if name == "Write-in" and raw != name:
                row["write_in_detail"] += ("; " if row["write_in_detail"] else "") + f"{raw}={ch.get('totalVotes')}"
        rows.extend(merged.values())
    for r in rows:
        for v in vtypes:
            r.setdefault(v, 0)
    return {"generated_at": gen}, rows, vtypes


def run(county: str, base: str, out_dir: Path, argv=None) -> int:
    ap = argparse.ArgumentParser(description=f"{county} County, OH results by vote type (Clarity)")
    ap.add_argument("--file", help="Parse a local detail.xml instead of downloading")
    ap.add_argument("--out", type=Path, default=out_dir)
    args = ap.parse_args(argv)
    if args.file:
        ver, xml = "local", Path(args.file).read_bytes()
    else:
        print(f"Downloading {base} (current version, detailxml.zip)", file=sys.stderr)
        ver, xml = fetch(base)
    meta, rows, vtypes = parse(xml)
    if not rows:
        raise SystemExit(f"{county}: no contests in Clarity export")
    print(f"{county}: clarity feed v{ver}, {len(rows)} rows, {len({r['race'] for r in rows})} races, "
          f"generated {meta['generated_at']}", file=sys.stderr)
    bad = [f"{r['race']} / {r['contestant']}: {sum(r[v] for v in vtypes)} vs {r['total']}"
           for r in rows if sum(r[v] for v in vtypes) != r["total"]]
    if bad:
        print(f"WARNING: {len(bad)} rows where vote types don't sum to the total:", file=sys.stderr)
        for b in bad[:10]:
            print("  " + b, file=sys.stderr)
    else:
        print("Vote-type sums match totals.", file=sys.stderr)
    fields = ["race_id", "race", "contestant", "party", "write_in", *vtypes, *TAIL, "write_in_detail"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.out.mkdir(parents=True, exist_ok=True)
    for name in (f"summary_wide_{stamp}.csv", "summary_wide_latest.csv"):
        with (args.out / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    print(f"Wrote {len(rows):,} rows -> {args.out / 'summary_wide_latest.csv'}", file=sys.stderr)
    return 0
