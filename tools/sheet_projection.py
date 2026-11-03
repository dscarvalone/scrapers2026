"""Build the 'projection' tab of the owner's election-night Google Sheet.

The post-election playbook, as formulas (reads 'validations', so it updates
with the data):
  a) a cutoff (default 90%) on Eday votes counted / the model's expected Eday
     votes; a county at or above it is "done";
  b) counties grouped done / not done;
  c) and by group (base / swing / rurals, from 'grouping');
  d) what's left of Eday, by algebra: done -> 0 left; not done -> expected Eday
     minus counted, at the county's current Eday 2-way share (the model's
     expected Eday share until any Eday votes are counted). E-night projected
     margin = current margin (AP) + that Eday-left margin.
  e) mail scenarios: per group, outstanding mail ballots and an assumed Brown
     2-way share of them -> mail margin -> final projected margin.

A county with no Eday count at all (no split and no first-drop estimate) is
"no Eday count": it is NOT extrapolated (no borrowed or modelled split), and
the summary shows how much of the expected vote that leaves out.

Inputs (B2, and the scenario table) are kept on rebuild. Outstanding mail
defaults to 0: type the boards' outstanding absentee counts once posted.
The share defaults to the model's vote-weighted expected mail 2-way share for
the group (falling back to its expected total 2-way share).

Writes only the 'projection' tab (plus its group-colour shading).
Usage:
    GSHEET_ID=<id> python -m tools.sheet_projection
"""

from __future__ import annotations

import os
import sys

from tools.push_sheet import PROD_IDS, session
from tools.sheet_palette import group_shading_rules
from tools.sheet_validations import FIRST, KEY, LAST

TAB = "projection"
N = LAST - FIRST + 1
GROUPS = ["base", "swing", "rurals"]

CUTOFF = "$B$2"
SCEN0 = 5          # scenario rows 5-7 (base, swing, rurals), total row 8
SUM0 = 12          # summary rows 12-15 (FINAL, base, swing, rurals)
HDR = 17           # county table header row
C0 = HDR + 1       # first county row (18)
C1 = C0 + N - 1    # last county row
V = "validations"


def county_row(r: int, v: int) -> list:
    return [
        f"={V}!A{v}",                                                    # A group
        f"={V}!B{v}",                                                    # B FIPS
        f"={V}!C{v}",                                                    # C county
        f'=IF({V}!P{v}="","",{V}!P{v})',                                 # D Eday votes counted
        f'=IF({V}!Q{v}="","",{V}!Q{v})',                                 # E expected Eday votes
        f'=IF(OR(D{r}="",E{r}="",N(E{r})=0),"",D{r}/E{r})',              # F % of expected
        f'=IF(F{r}="","no Eday count",IF(F{r}>={CUTOFF},"done","not done"))',  # G status
        f"=N({V}!AQ{v})-N({V}!AR{v})",                                   # H current margin (AP)
        f'=IF({V}!J{v}<>"",{V}!J{v},IF({V}!K{v}<>"",{V}!K{v},""))',      # I Eday 2-way share used
        f'=IF({V}!J{v}<>"","counted",IF({V}!K{v}<>"","model",""))',      # J share source
        f'=IF(G{r}="no Eday count","",IF(G{r}="done",0,MAX(0,E{r}-D{r})))',    # K Eday votes left
        f'=IF(OR(K{r}="",I{r}=""),"",(2*I{r}-1)*K{r})',                  # L Eday-left margin
        f"=H{r}+N(L{r})",                                                # M E-night projected margin
        f'=N({V}!U{v})',                                                 # N expected total votes
    ]


COUNTY_HDR = ["Group", "FIPS", "County", "Eday votes counted", "Expected Eday votes",
              "% of expected Eday", "Status", "Current margin (AP)", "Eday 2-way share used",
              "Share from", "Eday votes left", "Eday-left margin", "E-night projected margin",
              "Expected total votes"]


def scen_row(r: int, g: str, kept: dict) -> list:
    gr = f"{V}!$A${FIRST}:$A${LAST}"
    s = lambda col: f"SUMIFS({V}!${col}${FIRST}:${col}${LAST},{gr},$A{r})"
    default_share = (f"=IFERROR({s('BA')}/({s('BA')}+{s('BB')}),"
                     f"IFERROR({s('AS')}/({s('AS')}+{s('AT')}),0.5))")
    return [g,
            f"={s('AF')}",                                   # B model's expected mail ballots (context)
            kept.get((r, "C"), 0),                           # C outstanding mail ballots (input)
            kept.get((r, "D"), default_share),               # D Brown 2-way share of it (input)
            f"=(2*N(D{r})-1)*N(C{r})"]                       # E mail margin


def summary_row(r: int, g: str) -> list:
    crit = '"?*"' if g == "FINAL" else f"$A{r}"
    A, G = f"$A${C0}:$A${C1}", f"$G${C0}:$G${C1}"

    def cnt(status):
        return f'=COUNTIFS({A},{crit},{G},"{status}")'

    def sm(col, status=None):
        st = f',{G},"{status}"' if status else ""
        return f"SUMIFS(${col}${C0}:${col}${C1},{A},{crit}{st})"

    mail = f"=SUM(E{SCEN0}:E{SCEN0 + 2})" if g == "FINAL" else \
        f"=IFERROR(INDEX($E${SCEN0}:$E${SCEN0 + 2},MATCH($A{r},$A${SCEN0}:$A${SCEN0 + 2},0)),0)"
    return [g, cnt("done"), cnt("not done"), cnt("no Eday count"),
            f'=IFERROR({sm("N", "no Eday count")}/{sm("N")},"")',
            f"={sm('H')}", f"={sm('K')}", f"={sm('L')}", f"={sm('M')}",
            mail, f"=I{r}+J{r}"]


SUMMARY_HDR = ["Group", "Counties done", "Not done", "No Eday count", "Expected vote not projected",
               "Current margin (AP)", "Eday votes left", "Eday-left margin", "E-night projected margin",
               "Mail margin (scenario)", "Final projected margin"]


def build(sheet_id: str) -> None:
    if sheet_id in PROD_IDS:
        raise SystemExit("Refusing to write to the AP aggregator's production sheet.")
    s, _ = session(KEY)
    api = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    sheets = s.get(api, params={"fields": "sheets(properties,conditionalFormats)"}).json()["sheets"]
    tab = next((x for x in sheets if x["properties"]["title"] == TAB), None)
    kept: dict = {}
    if tab is None:
        gid = s.post(api + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}
                     ).json()["replies"][0]["addSheet"]["properties"]["sheetId"]
        ncf = 0
    else:
        gid, ncf = tab["properties"]["sheetId"], len(tab.get("conditionalFormats", []))
        # keep the owner's inputs
        cur = s.get(f"{api}/values/{TAB}!A1:E{SCEN0 + 2}", params={"valueRenderOption": "FORMULA"}).json()
        vals = cur.get("values", [])
        if len(vals) >= 2 and len(vals[1]) >= 2 and vals[1][1] != "":
            kept[(2, "B")] = vals[1][1]
        for r in range(SCEN0, SCEN0 + 3):
            row = vals[r - 1] if len(vals) >= r else []
            for i, col in ((2, "C"), (3, "D")):
                if len(row) > i and row[i] != "":
                    kept[(r, col)] = row[i]

    rows: list[list] = [[""] * 14 for _ in range(C1)]
    rows[0][0] = ("E-night projection: counties at or above the cutoff (Eday votes counted / model's expected "
                  "Eday votes) are done; the rest get expected-minus-counted Eday votes at their current Eday "
                  "share. Then mail scenarios.")
    rows[1][0:3] = ["Done cutoff (% of expected Eday)", kept.get((2, "B"), 0.9),
                    "<- input. Counties with no Eday count are not extrapolated (see 'Expected vote not projected')."]
    rows[3][0:5] = ["Mail scenario", "Model's expected mail ballots", "Outstanding mail ballots (input)",
                    "Brown 2-way share of it (input)", "Mail margin"]
    for i, g in enumerate(GROUPS):
        rows[SCEN0 - 1 + i][0:5] = scen_row(SCEN0 + i, g, kept)
    rows[SCEN0 + 2][0:5] = ["Total", f"=SUM(B{SCEN0}:B{SCEN0 + 2})", f"=SUM(C{SCEN0}:C{SCEN0 + 2})", "",
                            f"=SUM(E{SCEN0}:E{SCEN0 + 2})"]
    rows[SCEN0 + 3][0] = ("Outstanding mail: type the boards' outstanding absentee counts once posted. "
                          "Share defaults to the model's expected mail 2-way share for the group; type over it "
                          "to try a scenario.")
    rows[SUM0 - 2][0:11] = SUMMARY_HDR
    for i, g in enumerate(["FINAL"] + GROUPS):
        rows[SUM0 - 1 + i][0:11] = summary_row(SUM0 + i, g)
    rows[HDR - 1] = COUNTY_HDR
    for k in range(N):
        rows[C0 - 1 + k] = county_row(C0 + k, FIRST + k)

    req = [{"deleteConditionalFormatRule": {"sheetId": gid, "index": 0}} for _ in range(ncf)]
    req += [{"updateCells": {"range": {"sheetId": gid}, "fields": "userEnteredValue,userEnteredFormat"}},
            {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {
                "rowCount": C1, "columnCount": 14, "frozenRowCount": 0, "frozenColumnCount": 3}},
                "fields": "gridProperties(rowCount,columnCount,frozenRowCount,frozenColumnCount)"}}]
    s.post(api + ":batchUpdate", json={"requests": req}).raise_for_status()
    s.put(f"{api}/values/{TAB}!A1", params={"valueInputOption": "USER_ENTERED"},
          json={"values": rows}).raise_for_status()

    def rng(r0, r1, c0, c1):
        return {"sheetId": gid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}

    def fmt(r0, r1, c0, c1, pattern, typ="NUMBER"):
        return {"repeatCell": {"range": rng(r0, r1, c0, c1),
                               "cell": {"userEnteredFormat": {"numberFormat": {"type": typ, "pattern": pattern}}},
                               "fields": "userEnteredFormat.numberFormat"}}

    def bold(r0, r1, c0, c1):
        return {"repeatCell": {"range": rng(r0, r1, c0, c1),
                               "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "wrapStrategy": "WRAP"}},
                               "fields": "userEnteredFormat(textFormat,wrapStrategy)"}}

    input_bg = {"red": 1, "green": 0.95, "blue": 0.8}
    margin = "+#,##0;-#,##0;0"
    req = [bold(0, 1, 0, 1), bold(1, 2, 0, 1), bold(3, 4, 0, 5), bold(SUM0 - 2, SUM0 - 1, 0, 11),
           bold(HDR - 1, HDR, 0, 14), bold(SUM0 - 1, SUM0, 0, 11),
           fmt(1, 2, 1, 2, "0%", "PERCENT"),
           fmt(SCEN0 - 1, SCEN0 + 2, 1, 3, "#,##0"), fmt(SCEN0 - 1, SCEN0 + 2, 3, 4, "0.0%", "PERCENT"),
           fmt(SCEN0 - 1, SCEN0 + 2, 4, 5, margin), fmt(SCEN0 + 2, SCEN0 + 3, 1, 3, "#,##0"),
           fmt(SCEN0 + 2, SCEN0 + 3, 4, 5, margin), bold(SCEN0 + 2, SCEN0 + 3, 0, 5),
           fmt(SUM0 - 1, SUM0 + 3, 4, 5, "0%", "PERCENT"), fmt(SUM0 - 1, SUM0 + 3, 5, 6, margin),
           fmt(SUM0 - 1, SUM0 + 3, 6, 7, "#,##0"), fmt(SUM0 - 1, SUM0 + 3, 7, 11, margin),
           fmt(C0 - 1, C1, 3, 5, "#,##0"), fmt(C0 - 1, C1, 5, 6, "0%", "PERCENT"),
           fmt(C0 - 1, C1, 7, 8, margin), fmt(C0 - 1, C1, 8, 9, "0.0%", "PERCENT"),
           fmt(C0 - 1, C1, 10, 11, "#,##0"), fmt(C0 - 1, C1, 11, 13, margin), fmt(C0 - 1, C1, 13, 14, "#,##0"),
           {"repeatCell": {"range": rng(1, 2, 1, 2), "cell": {"userEnteredFormat": {"backgroundColor": input_bg}},
                           "fields": "userEnteredFormat.backgroundColor"}},
           {"repeatCell": {"range": rng(SCEN0 - 1, SCEN0 + 2, 2, 4),
                           "cell": {"userEnteredFormat": {"backgroundColor": input_bg}},
                           "fields": "userEnteredFormat.backgroundColor"}},
           {"updateBorders": {"range": rng(SUM0 - 1, SUM0, 0, 11), "bottom": {"style": "SOLID"}}}]
    # status colours
    for status, col in (("done", {"red": 0.72, "green": 0.88, "blue": 0.8}),
                        ("not done", {"red": 1, "green": 0.9, "blue": 0.6}),
                        ("no Eday count", {"red": 0.85, "green": 0.85, "blue": 0.85})):
        req.append({"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [rng(C0 - 1, C1, 6, 7)],
            "booleanRule": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": status}]},
                            "format": {"backgroundColor": col}}}}})
    # group colours (shared palette): scenario + summary labels, and county names by column A
    req += group_shading_rules(gid, [(SCEN0 - 1, SCEN0 + 2, 0, 1), (SUM0, SUM0 + 3, 0, 1),
                                     (C0 - 1, C1, 2, 3, "A")])
    req.append({"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS",
                                                        "startIndex": 0, "endIndex": 14},
                                              "properties": {"pixelSize": 120}, "fields": "pixelSize"}})
    r = s.post(api + ":batchUpdate", json={"requests": req})
    if r.status_code != 200:
        raise SystemExit(f"Format request failed: {r.status_code} {r.text[:400]}")
    print(f"projection: {N} counties, cutoff {rows[1][1]}, inputs kept: {sorted(kept)} -> {sheet_id}")


def main(argv=None) -> int:
    sheet_id = os.environ.get("GSHEET_ID")
    if not sheet_id:
        print("Set GSHEET_ID", file=sys.stderr)
        return 2
    build(sheet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
