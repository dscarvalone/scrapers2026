"""Build the `scraper_sources` tab for the DSCC Ohio election-night workbook.

The DSCC workbook already carries results, the vote-method block
(eday / evip / vbm / provisional / early, where early = evip + vbm),
2020-24 history, turnout and demographics, keyed on county_fips. This tab
adds ONLY what the workbook does not have: where each county's
vote-method split comes from, which of the workbook's method columns that
source can fill, label-mapping caveats, and when a split is expected.
`county_fips` is the join key; the county name is a lookup formula into
county_raw, not a copy.

Usage:
    python -m tools.build_sources_sheet <dscc_workbook.xlsx> <out_dir>
Writes <out_dir>/scraper_sources.csv (paste/import into Google Sheets) and
<out_dir>/<workbook name>_with_scraper_sources.xlsx (a copy of the
workbook with the tab appended; the original is not modified).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule

ROOT = Path(__file__).resolve().parent.parent
LAST_VERIFIED = "2026-11-01"
ACTIONS = {"Cuyahoga", "Franklin", "Montgomery", "Summit", "Hamilton", "Pickaway", "Hocking"}

# Workbook buckets: eday, evip (early in-person), vbm (mail), provisional;
# "early" = evip + vbm. "early*" means the source gives only the combined
# early/absentee number, so evip and vbm stay blank.
# county -> (label mapping, unmapped labels, mapping assumption)
SCRAPED = {
    "Allen": ("Election Day→eday; Absentee→early*; Provisional→provisional", "", ""),
    "Athens": ("Election Day→eday; Absentee In Office→evip; Absentee Mail Out→vbm; Provisional→provisional", "", ""),
    "Butler": ("Election Day→eday; Early Voting→evip; Absentee Voting→vbm; Provisional→provisional", "",
               "Absentee Voting = mail (ENR page setting hdnMailVote)"),
    "Carroll": ("Election Day→eday; Early Voting→evip; Mail Ballots→vbm; Provisional→provisional", "", ""),
    "Clark": ("Election Day→eday; Early Voting→evip; Absentee Ballots→vbm; Provisional→provisional", "",
              "Absentee Ballots = mail (inferred: separate Early Voting column)"),
    "Cuyahoga": ("Election Day→eday; Early In-Person→evip; Vote By Mail→vbm; Provisional→provisional",
                 "Post Election Day; Post VBM", "Post* columns not mapped pending county definition"),
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
                   "Absentee/Early Voting/Election Day Add-In", "Add-In groups not mapped"),
    "Paulding": ("Election Day→eday; Absentee→early*; Provisional→provisional", "", ""),
    "Pickaway": ("Election Day→eday; In Office Absentee→evip; Mail Absentee→vbm; Provisional→provisional", "", ""),
    "Preble": ("Election Day→eday; Absentee Early→evip; Absentee Mail→vbm; Provisional→provisional",
               "Absentee Late", "Absentee Late not mapped (likely late-arriving mail)"),
    "Stark": ("Election Day→eday; Early In Person→evip; Vote by Mail→vbm; Provisional→provisional", "", ""),
    "Summit": ("Polls→eday; Abs Walk-in→evip; Abs Mail→vbm; Provisional→provisional",
               "Timely Abs", "Timely Abs not mapped (likely late-arriving mail)"),
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
    "Clermont": "Election Day→eday; Absentee In-Person→evip; Absentee Mail→vbm; Provisional→provisional",
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

COLUMNS = [
    "county_fips", "county", "split_status", "source_platform", "runs_in", "source_url",
    "fills_eday", "fills_evip", "fills_vbm", "fills_provisional", "fills_early", "early_combined_only",
    "label_mapping", "unmapped_labels", "mapping_assumption",
    "history_split", "split_expected", "nov3_action", "evidence", "last_verified",
]


def fills(mapping: str) -> dict:
    m = mapping or ""
    combined = "→early*" in m
    out = {
        "fills_eday": "→eday" in m,
        "fills_evip": "→evip" in m,
        "fills_vbm": "→vbm" in m,
        "fills_provisional": "→provisional" in m,
        "early_combined_only": combined,
    }
    out["fills_early"] = combined or (out["fills_evip"] and out["fills_vbm"])
    return out


def build_rows(fips_by_county: dict[str, str]) -> list[dict]:
    rows = []
    for r in csv.DictReader((ROOT / "counties.csv").open()):
        c = r["county"]
        hs = r["history_split"]
        scraped = c in SCRAPED
        if r["status"] == "working":
            status = STATUSES[0]
        elif r["status"] == "pending_link":
            status = STATUSES[1]
        else:
            status = STATUSES[2]
        mapping, unmapped, assumption = SCRAPED.get(c, (EXPECTED.get(c, ""), "", ""))
        if not scraped and mapping:
            mapping = "EXPECTED: " + mapping
        f = fills(mapping) if scraped else {k: "" for k in fills("")}
        rows.append({
            "county_fips": fips_by_county[c],
            "county": None,  # formula, filled per row below
            "split_status": status,
            "source_platform": r["platform"] if scraped else "",
            "runs_in": ("GitHub Actions" if c in ACTIONS else "Local loop (Chrome)") if scraped else "",
            "source_url": r["results_page"] or r["boe_url"],
            **f,
            "label_mapping": mapping,
            "unmapped_labels": unmapped,
            "mapping_assumption": assumption,
            "history_split": hs,
            "split_expected": SPLIT_EXPECTED[hs],
            "nov3_action": NOV3_ACTION[hs],
            "evidence": r["history_evidence"] if not scraped else "",
            "last_verified": LAST_VERIFIED,
        })
    rows.sort(key=lambda x: x["county_fips"])
    return rows


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    src, out_dir = Path(argv[0]), Path(argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(src)
    raw = wb["county_raw"]
    hdr = [c.value for c in raw[1]]
    i_f, i_n = hdr.index("county_fips"), hdr.index("reporting_unit_name")
    fips = {}
    for row in raw.iter_rows(min_row=2, values_only=True):
        if row[i_f]:
            fips[row[i_n].replace(" County", "")] = str(row[i_f])
    rows = build_rows(fips)
    assert len(rows) == 88, len(rows)
    fcol = openpyxl.utils.get_column_letter(i_f + 1)
    ncol = openpyxl.utils.get_column_letter(i_n + 1)
    name_formula = "=IFERROR(INDEX(county_raw!${n}:${n},MATCH(TEXT(A{r},\"0\"),county_raw!${f}:${f},0)),\"\")"

    with (out_dir / "scraper_sources.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for k, r in enumerate(rows, start=2):
            r = {c: (("TRUE" if v else "FALSE") if isinstance(v, bool) else v) for c, v in r.items()}
            w.writerow({**r, "county": name_formula.format(n=ncol, f=fcol, r=k)})

    if "scraper_sources" in wb.sheetnames:
        del wb["scraper_sources"]
    ws = wb.create_sheet("scraper_sources")
    ws.append(COLUMNS)
    for k, r in enumerate(rows, start=2):
        ws.append([name_formula.format(n=ncol, f=fcol, r=k) if c == "county" else r[c] for c in COLUMNS])
        ws.cell(k, 1).number_format = "@"
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    widths = {"A": 11, "B": 16, "C": 30, "D": 20, "E": 19, "F": 40, "M": 60, "N": 26, "O": 40,
              "P": 26, "Q": 36, "R": 44, "S": 60, "T": 12}
    for col, wdt in widths.items():
        ws.column_dimensions[col].width = wdt
    n = len(rows) + 1
    dv = DataValidation(type="list", allow_blank=True, formula1='"' + ",".join(STATUSES) + '"')
    ws.add_data_validation(dv)
    dv.add(f"C2:C{n}")
    green = PatternFill("solid", fgColor="D9EAD3")
    amber = PatternFill("solid", fgColor="FFF2CC")
    ws.conditional_formatting.add(f"C2:C{n}", FormulaRule(formula=[f'LEFT($C2,8)="Itemized"'], fill=green))
    ws.conditional_formatting.add(f"Q2:Q{n}", FormulaRule(formula=[f'LEFT($Q2,13)="Election nigh"'], fill=green))
    ws.conditional_formatting.add(f"Q2:Q{n}", FormulaRule(formula=[f'LEFT($Q2,8)="Official"'], fill=amber))
    out = out_dir / (src.stem + "_with_scraper_sources.xlsx")
    wb.save(out)
    print(out)
    print(out_dir / "scraper_sources.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
