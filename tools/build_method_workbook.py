"""Build the standalone Ohio U.S. Senate vote-method workbook.

This is a sheet of its own, separate from the AP-based county aggregator.
It uses the aggregator's vocabulary so the two can be joined if wanted:
`county_fips` as the key, and method buckets named like its columns
(eday, evip, vbm, provisional, early; early = evip + vbm).

Tabs:
  votes_by_method   one row per county (88), a block of columns per method
                    bucket: <bucket>_total_votes, _dem_votes, _gop_votes,
                    _breakout_1_votes (Lib), _breakout_2_votes (Ind / other
                    party), _other_votes (write-ins). Blank = not reported.
  votes_long        one row per county x candidate x county vote-type label
                    (for pivots and auditing the bucket mapping)
  sources           where each county's split comes from, mapping caveats,
                    when a split is expected (the earlier metadata tab)
  about             column definitions and candidate mapping

Usage:
    python -m tools.build_method_workbook <out_dir>                # committed data/ files
    python -m tools.build_method_workbook <out_dir> --from-output  # latest local runs
Writes <out_dir>/OH_Senate_2026_vote_method.xlsx and one CSV per tab.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Font, PatternFill

from common import senate, timing
from tools import county_format
# Method buckets, candidate -> party column, and party columns are shared with
# the timing model (common/timing.py) so the tabs always agree.
from common.timing import BUCKET, CAND_COL, PARTY_COLS

ROOT = Path(__file__).resolve().parent.parent
LAST_VERIFIED = "2026-11-01"
WORKBOOK = "OH_Senate_2026_vote_method.xlsx"
# Counties scraped by the GitHub Actions workflow (its COUNTIES setting).
# Hamilton moved to the local loop on 2026-11-02 (its host blocks the runners).
ACTIONS = {"Cuyahoga", "Franklin", "Montgomery", "Summit", "Pickaway", "Hocking"}
BUCKETS = ["eday", "evip", "vbm", "early", "provisional", "unassigned"]

# --- sources tab --------------------------------------------------------
# county -> (label mapping, unmapped labels, mapping assumption).
# "early*" = the source gives only a combined early/absentee number.
SCRAPED = {
    "Allen": ("Election Day→eday; Absentee→early*; Provisional→provisional", "", ""),
    "Athens": ("Election Day→eday; Absentee In Office→evip; Absentee Mail Out→vbm; Provisional→provisional", "", ""),
    "Butler": ("Election Day→eday; Early Voting→evip; Absentee Voting→vbm; Provisional→provisional", "",
               "Absentee Voting = mail (ENR page setting hdnMailVote)"),
    "Carroll": ("Election Day→eday; Early Voting→evip; Mail Ballots→vbm; Provisional→provisional", "", ""),
    "Clark": ("Election Day→eday; Early Voting→evip; Absentee Ballots→vbm; Provisional→provisional", "",
              "Absentee Ballots = mail (inferred: separate Early Voting column)"),
    "Clermont": ("Election Day→eday; Absentee In-Person→evip; Absentee Mail→vbm; Provisional→provisional", "",
                 "Election-night file name not known in advance; scraper picks it from the results page"),
    "Cuyahoga": ("Election Day→eday; Early In-Person→evip; Vote By Mail→vbm; Provisional→provisional",
                 "Post Election Day; Post VBM", "Post* columns go to unassigned pending county definition"),
    "Erie": ("Election Day→eday; Absentee→early*; Provisional→provisional", "", ""),
    "Franklin": ("Election Day→eday; Early Voting→evip; Absentee Ballots→vbm; Provisional→provisional", "",
                 "Absentee Ballots = mail (inferred: separate Early Voting column)"),
    "Hamilton": ("Election→eday; Early→early*", "", "No provisional column; Early not defined by county, kept combined"),
    "Hocking": ("Election Day→eday; Early Voting→evip; Absentee→vbm; Provisional→provisional", "", ""),
    "Licking": ("Election Day→eday; Absentee Office→evip; Absentee Mail→vbm; Provisional→provisional", "", ""),
    "Lucas": ("Election Day→eday; Early Voting→evip; Absentee Ballots→vbm; Provisional→provisional", "",
              "Absentee Ballots = mail (inferred); feed has no Write-in line"),
    "Madison": ("Election Day→eday; Absentee Office→evip; Absentee Mail→vbm; Provisional→provisional", "", ""),
    "Miami": ("ED→eday; EV→evip; AB→vbm; PR→provisional", "",
              "Column order taken from printed header; not yet verified on real votes"),
    "Montgomery": ("Election Day→eday; Early Voting→evip; Absentee→vbm; Provisional→provisional",
                   "Absentee/Early Voting/Election Day Add-In", "Add-In groups go to unassigned"),
    "Paulding": ("Election Day→eday; Absentee→early*; Provisional→provisional", "", ""),
    "Pickaway": ("Election Day→eday; In Office Absentee→evip; Mail Absentee→vbm; Provisional→provisional", "", ""),
    "Preble": ("Election Day→eday; Absentee Early→evip; Absentee Mail→vbm; Provisional→provisional",
               "Absentee Late", "Absentee Late goes to unassigned (likely late-arriving mail)"),
    "Stark": ("Election Day→eday; Early In Person→evip; Vote by Mail→vbm; Provisional→provisional", "", ""),
    "Summit": ("Polls→eday; Abs Walk-in→evip; Abs Mail→vbm; Provisional→provisional",
               "Timely Abs", "Timely Abs goes to unassigned (likely late-arriving mail)"),
    "Van Wert": ("Election Day→eday; Early Voting→evip; Absentee Mail→vbm; Provisional→provisional", "", ""),
    "Warren": ("Election Day→eday; Early Voting→evip; Mail Ballots→vbm; Provisional→provisional", "", ""),
}
# Expected buckets for counties not scraped, from their past reports.
EXPECTED = {
    "Highland": "Election Day→eday; EV→evip; AB→vbm; PR→provisional (precinct PDF)",
    "Putnam": "Election Day→eday; Absentee→early*; Provisional→provisional (precinct PDF)",
    "Shelby": "Election Day→eday; In-Office→evip; Mail→vbm; Prov→provisional (precinct PDF)",
    "Auglaize": "Polling Place→eday; Early Voting Absentee→evip; Mail Absentee→vbm; Provisional→provisional",
    "Darke": "Polling Place→eday; Early Voting Absentee→evip; Mail Absentee→vbm; Provisional→provisional",
    "Coshocton": "Election Day→eday; Absentee→early*; Provisional→provisional",
    "Logan": "Election Day→eday; Early In-Person→evip; Absentee→vbm; Provisional→provisional; 17 Year Old unmapped",
    "Tuscarawas": "Election Day→eday; Absentee→early*; Provisional→provisional; ED Central Count, Absentee after ED unmapped",
    "Lake": "Election Day (+Paper)→eday; Early Vote→evip; ABS By Mail→vbm; Provisional→provisional",
    "Medina": "Election Day→eday; Early Voting→evip; Absentee→vbm; Provisional→provisional",
    "Columbiana": "Election Day→eday; In Office→evip; Absentee→vbm; Provisional→provisional",
}
SPLIT_EXPECTED = {
    "n/a_scraped": "Election night (scraper live)",
    "yes_election_night": "Election night (link not posted yet)",
    "yes_nov3_precinct_only": "Election night, precinct PDF only (parser not built)",
    "likely_yes_election_night": "Election night, likely (past election-night reports split)",
    "official_canvass_only": "Official canvass, ~Nov 17-24",
    "confirmed_no": "Not expected",
    "likely_no": "Not expected",
    "no_history_found": "Unknown",
}
NOV3_ACTION = {
    "n/a_scraped": "Monitor loop output",
    "yes_election_night": "Scraper picks up link automatically",
    "yes_nov3_precinct_only": "Build precinct-summing parser, or totals only",
    "likely_yes_election_night": "Recheck 8:30 + 9:30 PM (recheck_zero_reports --make-scrapers)",
    "official_canvass_only": "Recheck 8:30 + 9:30 PM; else wait for canvass",
    "confirmed_no": "None (totals only)",
    "likely_no": "Recheck 8:30 + 9:30 PM in case format changed",
    "no_history_found": "Recheck 8:30 + 9:30 PM",
}
STATUSES = ["Itemized - scraper live", "Itemized - waiting for link", "Not scraped - totals only"]
SOURCE_COLS = [
    "county_fips", "county", "split_status", "source_platform", "runs_in", "source_url",
    "fills_eday", "fills_evip", "fills_vbm", "fills_provisional", "fills_early", "early_combined_only",
    "label_mapping", "unmapped_labels", "mapping_assumption",
    "history_split", "split_expected", "nov3_action", "evidence", "last_verified",
]


def registry() -> list[dict]:
    return sorted(csv.DictReader((ROOT / "counties.csv").open(newline="")), key=lambda r: r["county_fips"])


def fills(mapping: str) -> dict:
    combined = "→early*" in mapping
    out = {"fills_eday": "→eday" in mapping, "fills_evip": "→evip" in mapping,
           "fills_vbm": "→vbm" in mapping, "fills_provisional": "→provisional" in mapping,
           "early_combined_only": combined}
    out["fills_early"] = combined or (out["fills_evip"] and out["fills_vbm"])
    return out


def source_rows(reg: list[dict]) -> list[dict]:
    rows = []
    for r in reg:
        c, hs = r["county"], r["history_split"]
        scraped = c in SCRAPED
        status = {"working": STATUSES[0], "pending_link": STATUSES[1]}.get(r["status"], STATUSES[2])
        mapping, unmapped, assumption = SCRAPED.get(c, (EXPECTED.get(c, ""), "", ""))
        if not scraped and mapping:
            mapping = "EXPECTED: " + mapping
        rows.append({
            "county_fips": r["county_fips"], "county": c, "split_status": status,
            "source_platform": r["platform"] if scraped else "",
            "runs_in": ("GitHub Actions" if c in ACTIONS else "Local loop (Chrome)") if scraped else "",
            "source_url": r["results_page"] or r["boe_url"],
            **(fills(mapping) if scraped else {k: "" for k in fills("")}),
            "label_mapping": mapping, "unmapped_labels": unmapped, "mapping_assumption": assumption,
            "history_split": hs, "split_expected": SPLIT_EXPECTED[hs], "nov3_action": NOV3_ACTION[hs],
            "evidence": "" if scraped else r["history_evidence"], "last_verified": LAST_VERIFIED,
        })
    return rows


# --- votes tabs ---------------------------------------------------------
def load_long(from_output: bool) -> tuple[list[dict], list[str], list[str]]:
    rel = Path("output/summary_wide_latest.csv") if from_output else Path("data/summary_wide.csv")
    rows, missing, failed = [], [], []
    for d in sorted(p for p in senate.COUNTIES_DIR.iterdir() if p.is_dir() and not p.name.startswith("_")):
        path = d / rel
        if not path.exists():
            missing.append(d.name)
            continue
        try:
            rows += senate.county_rows(d.name, path)
        except Exception as e:  # report, keep going: one bad county must not blank the sheet
            failed.append(f"{d.name}: {e}")
    return rows, missing, failed


ET = ZoneInfo("America/New_York")
STAMP_RE = re.compile(r"summary_wide_(\d{8}_\d{6})\.csv$")


def fetched_at(county_dir: Path, from_output: bool) -> tuple[str, str]:
    """Wall-clock time (ET) of the data in this county's row, and how it was found.

    - 'local run': newest counties/<c>/output/summary_wide_<stamp>.csv. Each
      scraper run writes one, named with the machine's local time, so this is
      the last successful fetch even when the numbers didn't change.
    - 'last commit': for counties the Actions bot scrapes, the commit time of
      data/summary_wide.csv (the bot commits only when numbers change, so this
      is the last change, not the last fetch).
    - 'file mtime': fallback when neither exists.
    """
    data = county_dir / "data" / "summary_wide.csv"
    name = county_dir.name.replace("_", " ").title()
    stamps = sorted(m.group(1) for p in (county_dir / "output").glob("summary_wide_*.csv")
                    if (m := STAMP_RE.search(p.name)))
    if stamps and (from_output or name not in ACTIONS):
        t = datetime.strptime(stamps[-1], "%Y%m%d_%H%M%S").astimezone()  # naive = this machine's zone
        return t.astimezone(ET).strftime("%Y-%m-%d %H:%M:%S %Z"), "local run"
    try:
        iso = subprocess.run(["git", "log", "-1", "--format=%cI", "--", str(data.relative_to(ROOT))],
                             cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        iso = ""
    if iso:
        return datetime.fromisoformat(iso).astimezone(ET).strftime("%Y-%m-%d %H:%M:%S %Z"), "last commit"
    if data.exists():
        return datetime.fromtimestamp(data.stat().st_mtime, ET).strftime("%Y-%m-%d %H:%M:%S %Z"), "file mtime"
    return "", ""


VOTE_META = ["county_fips", "county", "itemized", "fetched_at", "fetched_at_basis", "source_generated_at",
             "precincts_reported",
             "precincts_total", "early_combined_only", "unassigned_labels"]
VOTE_COLS = VOTE_META + [f"{b}_{p}_votes" for b in BUCKETS for p in ["total", *PARTY_COLS]] + ["method_sum_total_votes"]


def vote_rows(reg: list[dict], long_rows: list[dict],
              fetched: dict[str, tuple[str, str]] | None = None) -> tuple[list[dict], list[dict]]:
    fetched = fetched or {}
    by_county: dict[str, list[dict]] = {}
    for r in long_rows:
        by_county.setdefault(r["county"], []).append(r)
    wide, tidy = [], []
    for reg_row in reg:
        c = reg_row["county"]
        out = {k: "" for k in VOTE_COLS}
        out.update(county_fips=reg_row["county_fips"], county=c, itemized=c in by_county)
        rs = by_county.get(c, [])
        if rs:
            unassigned = sorted({r["method_county_label"] for r in rs if r["method"] not in BUCKET})
            buckets = {BUCKET.get(r["method"], "unassigned") for r in rs}
            out["fetched_at"], out["fetched_at_basis"] = fetched.get(c, ("", ""))
            out.update(source_generated_at=max(r["source_generated_at"] for r in rs),
                       precincts_reported=rs[0]["precincts_reported"], precincts_total=rs[0]["precincts_total"],
                       early_combined_only="early" in buckets and not {"evip", "vbm"} & buckets,
                       unassigned_labels="; ".join(unassigned))
            for b in buckets:
                for p in ["total", *PARTY_COLS]:
                    out[f"{b}_{p}_votes"] = 0
            for r in rs:
                b, p = BUCKET.get(r["method"], "unassigned"), CAND_COL[r["candidate"]]
                v = int(r["votes"])
                out[f"{b}_{p}_votes"] += v
                out[f"{b}_total_votes"] += v
            # early = evip + vbm when both are reported separately
            if {"evip", "vbm"} <= buckets:
                for p in ["total", *PARTY_COLS]:
                    out[f"early_{p}_votes"] = out[f"evip_{p}_votes"] + out[f"vbm_{p}_votes"]
            out["method_sum_total_votes"] = sum(
                out[f"{b}_total_votes"] for b in ["eday", "early", "provisional", "unassigned"]
                if out[f"{b}_total_votes"] != "")
            for r in rs:
                tidy.append({"county_fips": reg_row["county_fips"], "county": c, "candidate": r["candidate"],
                             "party_col": CAND_COL[r["candidate"]], "bucket": BUCKET.get(r["method"], "unassigned"),
                             "county_label": r["method_county_label"], "votes": int(r["votes"]),
                             "precincts_reported": r["precincts_reported"], "precincts_total": r["precincts_total"],
                             "fetched_at": out["fetched_at"], "source_generated_at": r["source_generated_at"]})
        wide.append(out)
    return wide, tidy


TIDY_COLS = ["county_fips", "county", "candidate", "party_col", "bucket", "county_label", "votes",
             "precincts_reported", "precincts_total", "fetched_at", "source_generated_at"]

ABOUT = [
    ("Purpose", "Ohio 2026 U.S. Senate results by vote method, from county sources scraped by "
                "dscarvalone/scrapers2026. Separate from the AP-based county aggregator; join on county_fips."),
    ("Built at", None),
    ("county_results (main tab)", "Same column names, order and definitions as the AP county aggregator's "
                                  "county_raw tab (its model columns exp_*, turnout, history and demographics "
                                  "are left out). Statewide row first, then 88 counties. method_source: "
                                  "itemized (county's own split; toplines from the same feed), first_drop "
                                  "(eday/early ESTIMATED, toplines from the SOS statewide site), totals_only. "
                                  "early = everything cast before Election Day. Statewide method columns sum "
                                  "only the counties that report that method; pct_<method> left blank there."),
    ("votes_by_timing", "Before vs on Election Day for all 88 counties. pre_eday = early in-person "
                                   "+ mail (incl. late-arriving mail); eday = Election Day; provisional kept "
                                   "separate (cast on Election Day or during early voting); unclassified = "
                                   "timing unknown. pre_eday_share_2way = pre_eday / (pre_eday + eday). "
                                   "has_mail_inperson_split = TRUE where votes_by_method also splits pre_eday "
                                   "into evip and vbm."),
    ("timing_source", "itemized = from the county's own vote-type split. first_drop = ESTIMATE for counties "
                      "with totals only: Ohio boards release absentee/early ballots first, so the county's last "
                      "statewide report with 0 precincts reporting is its pre_eday vote and growth since then is "
                      "eday (which then also holds any absentee or provisional ballots added after the first "
                      "precinct, so it leans toward eday). none = no clean first drop (first report already had "
                      "precincts) or no votes yet. For itemized counties first_drop_pre_eday_total_votes and "
                      "first_drop_check_diff show how well the estimate matched where the truth is known."),
    ("Buckets", "eday = Election Day; evip = early in-person (incl. in-office absentee); vbm = mail; "
                "provisional; early = evip + vbm, or the county's combined absentee number when it does not "
                "separate in-person from mail (early_combined_only = TRUE); unassigned = county vote types "
                "not yet mapped (listed in unassigned_labels)."),
    ("Candidates", "dem = Sherrod Brown; gop = Jon Husted; breakout_1 = William B. Redpath (Libertarian); "
                   "breakout_2 = Greg Levy (other-party, ASSUMED to be the aggregator's Ind column); "
                   "other = write-ins."),
    ("fetched_at", "Wall-clock time (ET) behind the row. fetched_at_basis 'local run' = the last successful "
                   "fetch on the loop machine (updates every cycle even if numbers are unchanged); 'last commit' "
                   "= counties the GitHub Actions bot scrapes: when the bot last committed new numbers (it "
                   "doesn't commit unchanged numbers, so this is the last change, not the last check); 'file "
                   "mtime' = fallback. source_generated_at is the county's own timestamp (a file fingerprint "
                   "for PDF counties)."),
    ("Blank vs 0", "Blank = the county's source does not report that bucket. 0 = reported, no votes yet."),
    ("method_sum_total_votes", "eday + early + provisional + unassigned. Should equal the county's "
                               "Senate total in the aggregator; a difference means a mapping or timing gap."),
    ("Non-itemized counties", "itemized = FALSE: no vote-method source; totals come from the aggregator."),
    ("Refresh", "python -m tools.build_method_workbook <out_dir> [--from-output], then re-import the CSVs "
                "(or the xlsx) into the Google Sheet."),
]


def replace_atomically(path: Path, write) -> None:
    """Write to a temp file in the same folder, then rename over `path`, so a
    reader (or an upload) never sees a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    try:
        write(Path(tmp))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_csv(path: Path, cols: list[str], rows: list[dict]):
    def write(p: Path):
        with p.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({c: ("TRUE" if v else "FALSE") if isinstance(v, bool) else v for c, v in r.items()})
    replace_atomically(path, write)


def add_tab(wb, title: str, cols: list[str], rows: list[dict], widths: dict | None = None, freeze="C2"):
    ws = wb.create_sheet(title)
    ws.append(cols)
    for r in rows:
        ws.append([r[c] for c in cols])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for k in range(2, len(rows) + 2):
        ws.cell(k, 1).number_format = "@"  # FIPS as text
    ws.freeze_panes = freeze
    ws.auto_filter.ref = ws.dimensions
    for col, w in (widths or {}).items():
        ws.column_dimensions[col].width = w
    return ws


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--from-output", action="store_true")
    args = ap.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    reg = registry()
    assert len(reg) == 88 and all(r["county_fips"] for r in reg)
    long_rows, missing, failed = load_long(args.from_output)
    names = {r["county"] for r in long_rows}
    fetched = {d.name.replace("_", " ").title(): fetched_at(d, args.from_output)
               for d in senate.COUNTIES_DIR.iterdir()
               if d.is_dir() and d.name.replace("_", " ").title() in names}
    wide, tidy = vote_rows(reg, long_rows, fetched)
    timing_rows = timing.timing_rows(reg, long_rows, timing.first_drop(timing.read_snapshots()))
    for r in timing_rows:  # wall-clock time for itemized rows (county stamps can be file fingerprints)
        if r["timing_source"] == "itemized" and r["county"] in fetched:
            r["as_of"] = fetched[r["county"]][0]
    sources = source_rows(reg)
    built_dt = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None, microsecond=0)
    built = built_dt.strftime("%Y-%m-%d %H:%M ET")
    results = county_format.county_rows(reg, wide, timing_rows, fetched,
                                        county_format.statewide_by_county(), built_dt)

    write_csv(args.out_dir / "county_results.csv", county_format.COLUMNS,
              [{k: (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else v) for k, v in r.items()}
               for r in results])
    write_csv(args.out_dir / "votes_by_timing.csv", timing.TIMING_COLS, timing_rows)
    write_csv(args.out_dir / "votes_by_method.csv", VOTE_COLS, wide)
    write_csv(args.out_dir / "votes_long.csv", TIDY_COLS, tidy)
    write_csv(args.out_dir / "sources.csv", SOURCE_COLS, sources)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    n = len(wide) + 1
    # Main tab: the aggregator's county_raw layout (same column names/order).
    ws = add_tab(wb, "county_results", county_format.COLUMNS, results, {"C": 20, "D": 22, "E": 18, "F": 18},
                 freeze="H2")
    for col_idx, name in enumerate(county_format.COLUMNS, start=1):
        if name.endswith("_votes") or name.endswith("_margin") or name in ("precincts_reported", "precincts_total"):
            fmt = "#,##0"
        elif name.endswith("_share") or name.endswith("two_way") or name.startswith("pct_"):
            fmt = "0.0%"
        elif name in ("latest_data_as_of", "refreshed_sheet_as_of"):
            fmt = "m/d/yyyy h:mm AM/PM"
        else:
            continue
        for row in range(2, len(results) + 2):
            ws.cell(row, col_idx).number_format = fmt
    ws["C2"].font = Font(bold=True)  # Statewide row
    src_col = openpyxl.utils.get_column_letter(county_format.COLUMNS.index("method_source") + 1)
    last = len(results) + 1
    for val, color in (("itemized", "D9EAD3"), ("first_drop", "FFF2CC"), ("totals_only", "EFEFEF")):
        ws.conditional_formatting.add(f"{src_col}2:{src_col}{last}", FormulaRule(
            formula=[f'${src_col}2="{val}"'], fill=PatternFill("solid", fgColor=color)))
    ws = add_tab(wb, "votes_by_timing", timing.TIMING_COLS, timing_rows,
                 {"B": 12, "C": 13, "D": 24, "G": 12, "H": 12, "I": 70})
    green, amber, grey = (PatternFill("solid", fgColor=c) for c in ("D9EAD3", "FFF2CC", "EFEFEF"))
    ws.conditional_formatting.add(f"C2:C{n}", FormulaRule(formula=['$C2="itemized"'], fill=green))
    ws.conditional_formatting.add(f"C2:C{n}", FormulaRule(formula=['$C2="first_drop"'], fill=amber))
    ws.conditional_formatting.add(f"C2:C{n}", FormulaRule(formula=['$C2="none"'], fill=grey))
    ws = add_tab(wb, "votes_by_method", VOTE_COLS, wide, {"B": 12, "D": 24, "E": 14, "F": 24, "J": 30})
    ws.conditional_formatting.add(f"C2:C{n}", FormulaRule(formula=["$C2=TRUE"],
                                  fill=PatternFill("solid", fgColor="D9EAD3")))
    add_tab(wb, "votes_long", TIDY_COLS, tidy, {"B": 12, "C": 20, "F": 26, "J": 24})
    ws = add_tab(wb, "sources", SOURCE_COLS, sources,
                 {"B": 12, "C": 26, "D": 20, "E": 19, "F": 40, "M": 60, "N": 26, "O": 40,
                  "P": 26, "Q": 36, "R": 44, "S": 60, "T": 12})
    ws.conditional_formatting.add(f"C2:C{n}", FormulaRule(formula=['LEFT($C2,8)="Itemized"'],
                                  fill=PatternFill("solid", fgColor="D9EAD3")))
    ws.conditional_formatting.add(f"Q2:Q{n}", FormulaRule(formula=['LEFT($Q2,8)="Official"'],
                                  fill=PatternFill("solid", fgColor="FFF2CC")))
    about = wb.create_sheet("about")
    about.append(["item", "description"])
    for k, v in ABOUT:
        about.append([k, built if v is None else v])
    about.append(["Counties with data", ", ".join(sorted({r["county"] for r in long_rows})) or "none"])
    about.append(["No data file yet", ", ".join(missing) or "none"])
    if failed:
        about.append(["Parse errors", " | ".join(failed)])
    about["A1"].font = about["B1"].font = Font(bold=True)
    about.column_dimensions["A"].width = 24
    about.column_dimensions["B"].width = 120
    out = args.out_dir / WORKBOOK
    replace_atomically(out, lambda p: wb.save(p))

    itemized = sum(1 for r in wide if r["itemized"])
    print(f"{out}: {itemized} counties itemized, {len(tidy)} long rows", file=sys.stderr)
    if missing:
        print(f"No data file yet: {', '.join(missing)}", file=sys.stderr)
    for f in failed:
        print(f"ERROR {f}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
