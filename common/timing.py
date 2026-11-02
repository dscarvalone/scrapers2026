"""Before vs on Election Day: the Senate vote by WHEN it was cast, for all 88 counties.

The split that matters is pre-Election-Day (early in-person + mail) vs
Election Day. Whether a county separates in-person from mail doesn't matter
here, so every county with any vote-method split can fill it, and counties
with totals only get an estimate from the order Ohio counts ballots in.

Timing classes:
  pre_eday      cast before Election Day: early in-person, mail, combined
                absentee, and late-arriving mail (Cuyahoga Post VBM, Summit
                Timely Abs, Preble Absentee Late: mail must be postmarked
                before Election Day)
  eday          cast on Election Day at the polls
  provisional   kept separate: cast at the polls on Election Day or during
                early voting, and the counties don't say which
  unclassified  vote types whose timing isn't known (Cuyahoga Post Election Day)

Sources, best first:
  itemized      a county feed with a vote-method split (counties/*/data/)
  first_drop    totals-only counties. Ohio boards tabulate absentee and early
                in-person ballots before polls close and release them first,
                before any Election Day precinct. So a county's last statewide
                snapshot with 0 precincts reporting (and votes > 0) is its
                pre-Election-Day vote, and growth since then is counted as
                Election Day. That later growth also holds any absentee or
                provisional ballots added after the first precinct, so the
                estimate leans toward Election Day; see `notes`.
  none          no split yet: no votes, or the county's first report already
                included precincts (no clean first drop to read).

Snapshots: every run appends the statewide county totals to
results/statewide_snapshots.csv when a county's numbers changed. That file
is the time series the first-drop estimate reads, so it must be kept (the
local loop commits it).

Usage:
    python -m common.timing          # append a snapshot, write results/senate_by_timing.csv
    python -m common.timing --no-snapshot
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
STATEWIDE = RESULTS / "senate_statewide_by_county.csv"
SNAPSHOTS = RESULTS / "statewide_snapshots.csv"
OUT = RESULTS / "senate_by_timing.csv"

# Common method name (common/senate.py) -> method bucket used in the workbook.
BUCKET = {
    "Election Day": "eday",
    "Early In-Person": "evip",
    "Mail": "vbm",
    "Provisional": "provisional",
    "Absentee (early in-person + mail)": "early",
}
# Common method name, or a county's own label when it isn't mapped -> timing.
TIMING = {
    "Election Day": "eday",
    "Early In-Person": "pre_eday",
    "Mail": "pre_eday",
    "Absentee (early in-person + mail)": "pre_eday",
    "Provisional": "provisional",
    # Unmapped county labels, classified by timing only:
    "Post VBM": "pre_eday",             # Cuyahoga: mail counted after Election Day
    "Timely Abs": "pre_eday",           # Summit: timely (postmarked) absentee arriving late
    "Absentee Late": "pre_eday",        # Preble: same
    "Absentee Add-In": "pre_eday",      # Montgomery: added-in ballots, by voting group
    "Early Voting Add-In": "pre_eday",
    "Election Day Add-In": "eday",
    "Post Election Day": "unclassified",  # Cuyahoga: likely provisional; timing not stated
}
TIMINGS = ["pre_eday", "eday", "provisional", "unclassified"]
CAND_COL = {
    "Sherrod Brown": "dem",
    "Jon Husted": "gop",
    "William B. Redpath": "breakout_1",  # Libertarian
    "Greg Levy": "breakout_2",           # other-party candidate (ASSUMED: the aggregator's Ind column)
    "Write-in": "other",
}
PARTY_COLS = ["dem", "gop", "breakout_1", "breakout_2", "other"]
SNAP_FIELDS = ["fetched_at", "county", "candidate", "votes", "precincts_reported", "precincts_total"]


def _et(iso: str) -> str:
    """Statewide fetched_at (UTC ISO) -> 'YYYY-MM-DD HH:MM:SS EST/EDT'. Non-ISO passes through."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        return datetime.fromisoformat(iso).astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S %Z")
    except (TypeError, ValueError):
        return iso


def timing_of(row: dict) -> str:
    """Timing class for one long row from common.senate.county_rows."""
    return TIMING.get(row["method"]) or TIMING.get(row["method_county_label"]) or "unclassified"


# --- snapshots ----------------------------------------------------------
def _key(rows: list[dict]) -> tuple:
    return tuple(sorted((r["candidate"], str(r["votes"]), str(r["precincts_reported"])) for r in rows))


def read_snapshots(path: Path = SNAPSHOTS) -> list[dict]:
    if not path.exists():
        return []
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


def append_snapshot(statewide: Path = STATEWIDE, path: Path = SNAPSHOTS) -> int:
    """Append each county whose statewide numbers changed since its last
    snapshot. Returns the number of counties appended."""
    if not statewide.exists():
        return 0
    current: dict[str, list[dict]] = {}
    for r in csv.DictReader(statewide.open(newline="", encoding="utf-8")):
        current.setdefault(r["county"].strip(), []).append(r)
    last: dict[str, list[dict]] = {}
    for r in read_snapshots(path):
        last.setdefault(r["county"], [])
        if last[r["county"]] and last[r["county"]][0]["fetched_at"] != r["fetched_at"]:
            last[r["county"]] = []
        last[r["county"]].append(r)
    changed = [c for c, rs in current.items() if c not in last or _key(rs) != _key(last[c])]
    if not changed:
        return 0
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SNAP_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for c in sorted(changed):
            for r in current[c]:
                w.writerow({**r, "county": c})
    return len(changed)


def first_drop(snapshots: list[dict]) -> dict[str, dict]:
    """Per county: pre-Election-Day votes by candidate from the last snapshot
    with 0 precincts reporting, and the latest totals."""
    by: dict[str, dict[str, list[dict]]] = {}
    for r in snapshots:
        by.setdefault(r["county"], {}).setdefault(r["fetched_at"], []).append(r)
    out = {}
    for county, snaps in by.items():
        times = sorted(snaps)
        latest = snaps[times[-1]]
        votes = lambda rs: {r["candidate"]: int(r["votes"] or 0) for r in rs}
        precincts = lambda rs: int(rs[0]["precincts_reported"] or 0)
        zero = [t for t in times if precincts(snaps[t]) == 0 and sum(votes(snaps[t]).values()) > 0]
        res = {"latest": votes(latest), "latest_at": times[-1], "latest_precincts": precincts(latest),
               "precincts_total": latest[0]["precincts_total"], "pre": None, "pre_at": ""}
        if sum(res["latest"].values()) == 0:
            res["status"] = "no_votes_yet"
        elif zero:
            res.update(pre=votes(snaps[zero[-1]]), pre_at=zero[-1])
            res["status"] = "first_drop" if res["latest_precincts"] > 0 else "first_drop_pre_only"
        else:
            res["status"] = "no_clean_first_drop"
        out[county] = res
    return out


# --- model --------------------------------------------------------------
TIMING_META = ["county_fips", "county", "timing_source", "as_of", "precincts_reported", "precincts_total",
               "pre_eday_share_2way", "has_mail_inperson_split", "notes"]
TIMING_COLS = (TIMING_META + [f"{t}_{p}_votes" for t in TIMINGS for p in ["total", *PARTY_COLS]]
               + ["total_votes", "first_drop_pre_eday_total_votes", "first_drop_check_diff"])


def _blank_block(out: dict, t: str):
    for p in ["total", *PARTY_COLS]:
        out[f"{t}_{p}_votes"] = 0


def _add(out: dict, t: str, cand: str, v: int):
    out[f"{t}_{CAND_COL[cand]}_votes"] += v
    out[f"{t}_total_votes"] += v


def timing_rows(reg: list[dict], long_rows: list[dict], drops: dict[str, dict]) -> list[dict]:
    """One row per county. `reg` rows need county and county_fips; `long_rows`
    are common.senate.county_rows output (county feeds only)."""
    by_county: dict[str, list[dict]] = {}
    for r in long_rows:
        by_county.setdefault(r["county"], []).append(r)
    rows = []
    for g in reg:
        c = g["county"]
        out = {k: "" for k in TIMING_COLS}
        out.update(county_fips=g["county_fips"], county=c)
        d = drops.get(c)
        rs = by_county.get(c)
        notes = []
        if rs:
            out["timing_source"] = "itemized"
            out.update(as_of=max(r["source_generated_at"] for r in rs),
                       precincts_reported=rs[0]["precincts_reported"], precincts_total=rs[0]["precincts_total"])
            buckets = {BUCKET.get(r["method"]) for r in rs}
            out["has_mail_inperson_split"] = {"evip", "vbm"} <= buckets  # detail in votes_by_method
            present = {timing_of(r) for r in rs}
            for t in present:
                _blank_block(out, t)
            for r in rs:
                _add(out, timing_of(r), r["candidate"], int(r["votes"]))
            if "provisional" not in present:
                notes.append("county reports no provisional column")
            odd = sorted({r["method_county_label"] for r in rs if r["method"] not in BUCKET})
            if odd:
                notes.append("timing assigned to unmapped vote types: " + ", ".join(
                    f"{l}→{TIMING.get(l, 'unclassified')}" for l in odd))
            if d and d.get("pre") is not None:
                fd = sum(d["pre"].values())
                out["first_drop_pre_eday_total_votes"] = fd
                out["first_drop_check_diff"] = fd - out["pre_eday_total_votes"]
        elif d and d["status"] in ("first_drop", "first_drop_pre_only"):
            out["timing_source"] = "first_drop"
            out["has_mail_inperson_split"] = False
            out.update(as_of=_et(d["latest_at"]), precincts_reported=d["latest_precincts"],
                       precincts_total=d["precincts_total"])
            _blank_block(out, "pre_eday")
            _blank_block(out, "eday")
            for cand, v in d["pre"].items():
                _add(out, "pre_eday", cand, v)
            for cand, v in d["latest"].items():
                _add(out, "eday", cand, v - d["pre"].get(cand, 0))
            minor_down = [p for p in ("breakout_1", "breakout_2", "other") if out[f"eday_{p}_votes"] < 0]
            if any(out[f"eday_{p}_votes"] < 0 for p in ("dem", "gop")):
                notes.append("ANOMALY: Brown's or Husted's total fell after the first drop; split not usable")
                for t in ("pre_eday", "eday"):
                    for p in ["total", *PARTY_COLS]:
                        out[f"{t}_{p}_votes"] = ""
                out["timing_source"] = "none"
            else:
                notes.append(f"estimate: pre_eday = last report with 0 precincts ({_et(d['pre_at'])}); "
                             "eday = growth since, incl. any absentee/provisional added later")
                if d["status"] == "first_drop_pre_only":
                    notes.append("no Election Day precincts reported yet")
                if minor_down:
                    notes.append("minor-candidate total fell after the first drop (" + ", ".join(minor_down)
                                 + "); their eday column is negative, Brown/Husted unaffected")
        else:
            out["timing_source"] = "none"
            if d:
                out.update(as_of=_et(d["latest_at"]), precincts_reported=d["latest_precincts"],
                           precincts_total=d["precincts_total"])
                notes.append({"no_votes_yet": "no votes reported yet",
                              "no_clean_first_drop": "first report already included precincts; "
                                                     "totals only"}.get(d["status"], d["status"]))
            else:
                notes.append("no statewide snapshot yet")
        if out["timing_source"] != "none" or (d and d.get("latest")):
            if rs:
                out["total_votes"] = sum(out[f"{t}_total_votes"] for t in TIMINGS if out[f"{t}_total_votes"] != "")
            elif d:
                out["total_votes"] = sum(d["latest"].values())
        pre, ed = out["pre_eday_total_votes"], out["eday_total_votes"]
        if pre != "" and ed != "" and pre + ed > 0:
            out["pre_eday_share_2way"] = round(pre / (pre + ed), 4)
        out["notes"] = "; ".join(notes)
        rows.append(out)
    return rows


def load_registry() -> list[dict]:
    return sorted(csv.DictReader((ROOT / "counties.csv").open(newline="")), key=lambda r: r["county_fips"])


def load_itemized(from_output: bool = False) -> tuple[list[dict], list[str], list[str]]:
    from common import senate
    rel = Path("output/summary_wide_latest.csv") if from_output else Path("data/summary_wide.csv")
    rows, missing, failed = [], [], []
    for d in sorted(p for p in senate.COUNTIES_DIR.iterdir() if p.is_dir() and not p.name.startswith("_")):
        path = d / rel
        if not path.exists():
            missing.append(d.name)
            continue
        try:
            rows += senate.county_rows(d.name, path)
        except Exception as e:  # one bad county must not blank the rest
            failed.append(f"{d.name}: {e}")
    return rows, missing, failed


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-snapshot", action="store_true", help="Don't append to the snapshot log")
    ap.add_argument("--from-output", action="store_true", help="Itemized data from local output/ runs")
    args = ap.parse_args(argv)
    if not args.no_snapshot:
        n = append_snapshot()
        print(f"Snapshot: {n} counties changed" if n else "Snapshot: no change", file=sys.stderr)
    long_rows, _missing, failed = load_itemized(args.from_output)
    rows = timing_rows(load_registry(), long_rows, first_drop(read_snapshots()))
    write_csv(OUT, TIMING_COLS, rows)
    from collections import Counter
    print(f"Timing: {dict(Counter(r['timing_source'] for r in rows))} -> {OUT}", file=sys.stderr)
    for f in failed:
        print(f"ERROR {f}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
