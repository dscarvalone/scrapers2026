"""Rehearsal data for the owner's Google Sheet: a FAKE county_results feed,
pushed to the `methods` tab only (via tools/push_sheet.py).

Starts from the AP test numbers in the sheet's `dscc data tab` (read only,
never written) so the fake feed agrees with the Topline's AP columns, then
splits each county's Brown / Husted / other votes into Election Day and
early. Early leans Democratic, Election Day Republican, as in Ohio's recent
results. The county mix copies what election night will look like:
  - the 22 counties we itemize: eday, evip, vbm, provisional (Hamilton,
    Erie, Paulding, Allen: combined early only)
  - most other counties: eday + early only (method_source = first_drop)
  - the 12 smallest counties: totals only (blank methods), to exercise the
    Topline's fallback to the model's share
Every row's notes say TEST DATA. Fixed random seed, so reruns are identical.

Usage:
    GSHEET_ID=<id> python -m tools.make_test_feed            # build + push
    GSHEET_ID=<id> python -m tools.make_test_feed --no-push  # just write the CSV
Restore real data afterwards (or let the loop do it on its next cycle):
    python -m tools.build_method_workbook ../exports && GSHEET_ID=<id> python -m tools.push_sheet
"""

from __future__ import annotations

import csv
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tools import county_format as cf
from tools.build_method_workbook import SCRAPED, registry
from tools.push_sheet import API, DEFAULT_KEY, push, session

OUT = Path(os.environ.get("TEST_FEED_OUT", Path(__file__).resolve().parent.parent.parent / "exports"
                          / "TEST_county_results.csv"))
COMBINED_ONLY = {"Hamilton", "Erie", "Paulding", "Allen"}
PARTIES = cf.PARTY_COLS


def ap_rows(sheet_id: str) -> dict[str, dict]:
    s, _ = session(Path(os.environ.get("GSHEET_KEY", DEFAULT_KEY)).expanduser())

    def get(rng, render):
        r = s.get(f"{API}/{sheet_id}/values/{rng}", params={"valueRenderOption": render}, timeout=30)
        r.raise_for_status()
        return r.json().get("values", [])
    hdr = [str(h).strip() for h in get("'dscc data tab'!A6:ZZ6", "FORMATTED_VALUE")[0]]
    out = {}
    for row in get("'dscc data tab'!A7:ZZ100", "UNFORMATTED_VALUE"):
        d = dict(zip(hdr, row))
        name = str(d.get("reporting_unit_name", ""))
        if name.endswith(" County"):
            out[name[:-7]] = d
    return out


def split(rng: random.Random, votes: dict[str, int], early_frac: float, lean: float):
    """Split per-party votes into (early, eday) so early leans D by `lean` (share points)."""
    tot = sum(votes.values())
    early_n = round(tot * early_frac)
    d, g = votes["dem"], votes["gop"]
    two = d + g
    base = d / two if two else 0.5
    e_share = min(max(base + lean * (1 - early_frac), 0.02), 0.98)  # keeps eday share in range too
    e_two = round(early_n * (two / tot)) if tot else 0
    early = {"dem": min(d, round(e_two * e_share))}
    early["gop"] = min(g, e_two - early["dem"])
    for p in ("breakout_1", "breakout_2", "other"):
        early[p] = round(votes[p] * early_frac)
    eday = {p: votes[p] - early[p] for p in PARTIES}
    return early, eday


def build(sheet_id: str) -> list[dict]:
    rng = random.Random(20261103)
    ap = ap_rows(sheet_id)
    statewide = cf.statewide_by_county()
    reg = registry()
    small = {r["county"] for r in sorted(reg, key=lambda r: ap.get(r["county"], {}).get("total_votes") or 0)[:12]}
    now = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None, microsecond=0)
    rows = []
    for g in sorted(reg, key=lambda r: r["county"]):
        c = g["county"]
        a = ap.get(c, {})
        votes = {p: int(a.get(f"{p}_votes") or 0) for p in PARTIES}
        out = {k: "" for k in cf.COLUMNS}
        out.update(state_code="OH", county_fips=g["county_fips"], reporting_unit_name=f"{c} County",
                   refreshed_sheet_as_of=now, latest_data_as_of=now)
        cf._fill_toplines(out, votes)
        ptot = int((statewide.get(c) or {}).get("precincts_total") or 0)
        out["precincts_total"] = ptot
        out["precincts_reported"] = round(ptot * float(a.get("pct_precincts_in") or 0))
        out["pct_precincts_in"] = cf._ratio(out["precincts_reported"], ptot)
        out["reporting_status"] = cf._status(out["precincts_reported"], ptot, out["total_votes"])
        if c in SCRAPED:
            src = "itemized"
        elif c in small:
            src = "totals_only"
        else:
            src = "first_drop"
        out["method_source"] = src
        if src != "totals_only" and out["total_votes"]:
            early_frac = rng.uniform(0.30, 0.55)
            early, eday = split(rng, votes, early_frac, lean=rng.uniform(0.08, 0.16))
            if src == "itemized":
                prov = {p: round(eday[p] * 0.012) for p in PARTIES}
                eday = {p: eday[p] - prov[p] for p in PARTIES}
                cf._fill_block(out, "provisional", prov)
                if c not in COMBINED_ONLY:
                    vbm_frac = rng.uniform(0.45, 0.70)
                    vbm = {p: round(early[p] * vbm_frac) for p in PARTIES}
                    cf._fill_block(out, "vbm", vbm)
                    cf._fill_block(out, "evip", {p: early[p] - vbm[p] for p in PARTIES})
                if c == "Hamilton":
                    for k in cf.method_cols("provisional"):
                        out[k] = ""   # Hamilton reports no provisional column
                    eday = {p: eday[p] + prov[p] for p in PARTIES}
            cf._fill_block(out, "eday", eday)
            cf._fill_block(out, "early", early)
            out["has_mail_inperson_split"] = src == "itemized" and c not in COMBINED_ONLY
            for m in cf.METHODS:
                out[f"pct_{m}"] = cf._ratio(out[f"{m}_total_votes"], out["total_votes"])
        out["notes"] = "TEST DATA (tools/make_test_feed.py), not real results"
        rows.append(out)
    sw = cf.statewide_row(rows, now)   # precincts summed from the test rows, not the real feed
    sw["notes"] = "TEST DATA; " + sw["notes"]
    return [sw] + rows


def check(rows: list[dict]) -> list[str]:
    """Sanity: no negative votes; methods add up to total votes where split."""
    bad = []
    for r in rows[1:]:
        for k, v in r.items():
            if k.endswith("_votes") and isinstance(v, int) and v < 0:
                bad.append(f"{r['reporting_unit_name']} {k}={v}")
        if r["eday_total_votes"] != "":
            parts = r["eday_total_votes"] + r["early_total_votes"] + (r["provisional_total_votes"] or 0)
            if parts != r["total_votes"]:
                bad.append(f"{r['reporting_unit_name']}: eday+early+prov {parts} != total {r['total_votes']}")
        if r["evip_total_votes"] != "" and r["evip_total_votes"] + r["vbm_total_votes"] != r["early_total_votes"]:
            bad.append(f"{r['reporting_unit_name']}: evip+vbm != early")
    return bad


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    sheet_id = os.environ.get("GSHEET_ID", "").strip()
    if not sheet_id:
        print("Set GSHEET_ID to your own sheet's ID", file=sys.stderr)
        return 2
    rows = build(sheet_id)
    problems = check(rows)
    if problems:
        print("Not pushing; test data failed its own checks:\n  " + "\n  ".join(problems[:20]), file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cf.COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else
                            ("TRUE" if v is True else "FALSE" if v is False else v)) for k, v in r.items()})
    from collections import Counter
    print(f"Wrote {OUT}: {len(rows)} rows, {dict(Counter(r['method_source'] for r in rows[1:]))}", file=sys.stderr)
    if "--no-push" in args:
        return 0
    return push(OUT, sheet_id, os.environ.get("GSHEET_TAB", "methods"),
                Path(os.environ.get("GSHEET_KEY", DEFAULT_KEY)).expanduser())


if __name__ == "__main__":
    sys.exit(main())
