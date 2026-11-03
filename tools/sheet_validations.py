"""Build the 'validations' tab of the owner's election-night Google Sheet.

Per county, and for FINAL + each group (base / swing / rurals, from the
'grouping' tab): Brown's 2-way share and turnout by vote method, compared with
the model's expectations in 'dscc data tab'. Everything is a formula reading
the 'methods', 'dscc data tab' and 'grouping' tabs; this script writes only
the 'validations' tab (clears and rewrites it in place, so its link is kept).

Layout (mirrors Topline):
  rows 1-2   headers
  row 3      FINAL (statewide)
  rows 4-6   base, swing, rurals
  rows 8-9   headers repeated
  rows 10-97 the 88 counties

Group rows are computed from SUMMED votes (never averaged shares), and each
comparison uses only the counties that have both an actual and an expected
value for it, so actual and expected always cover the same counties. The
vote sums come from hidden helper columns (AI onward).

Usage:
    GSHEET_ID=<id> python -m tools.sheet_validations
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from tools.push_sheet import PROD_IDS, session
from tools.sheet_palette import group_shading_rules

TAB = "validations"
KEY = Path.home() / ".config/scrapers2026/google-sa.json"
GROUPS = ["FINAL", "base", "swing", "rurals"]  # rows 3-6
FIRST, LAST = 10, 97  # county rows

# method key -> (label, actual source, actual prefix, expected prefix,
#               share cols (actual, expected, diff), vote cols (actual, expected, pct), helper start)
METHODS = {
    "eday": ("Eday", "M", "eday_", "eday_exp_", (9, 10, 3), (15, 16, 6), 34),
    "early": ("Early", "M", "early_", "early_exp_", (11, 12, 4), (17, 18, 7), 38),
    "total": ("Total (AP)", "A", "", "exp_", (13, 14, 5), (19, 20, 8), 42),
    "evip": ("In-person early", "M", "evip_", "evip_exp_", (21, 22, 23), (27, 28, 29), 46),
    "vbm": ("Mail", "M", "vbm_", "vbm_exp_", (24, 25, 26), (30, 31, 32), 50),
}
SOURCE_COL = 33
NCOLS = 54  # 34 visible + 20 helpers


def L(i: int) -> str:
    """0-based column index -> A1 letters."""
    s, i = "", i + 1
    while i:
        i, rm = divmod(i - 1, 26)
        s = chr(65 + rm) + s
    return s


def M(name: str, r: int) -> str:
    return f'IFERROR(VLOOKUP($C{r}, methods!$C$1:$ZZ$999, MATCH("{name}", methods!$1:$1, 0)-2, FALSE),"")'


def A(name: str, r: int) -> str:
    return (f"IFERROR(VLOOKUP($C{r}, 'dscc data tab'!$D$1:$ZZ$999, "
            f"MATCH(\"{name}\", 'dscc data tab'!$D$6:$ZZ$6, 0), FALSE),\"\")")


def headers() -> tuple[list, list, dict]:
    h1, h2, kinds = [""] * NCOLS, [""] * NCOLS, {}
    h2[0:3] = ["Group", "FIPS", "County"]
    h1[3], h1[6], h1[9], h1[15] = ("Key: Dem 2-way vs expected (pts)", "Key: turnout, % of expected",
                                   "Dem 2-way detail", "Turnout detail")
    h1[21], h1[27] = "Mail / in-person early: Dem 2-way", "Mail / in-person early: turnout"
    for m, (lab, _, _, _, (sa, se, sd), (va, ve, vp), hs) in METHODS.items():
        short = lab if m in ("eday", "early", "total") else lab
        if m in ("eday", "early", "total"):
            h2[sd], h2[vp] = short, short
            h2[sa], h2[se] = (f"{lab} actual" if m != "total" else "Total actual (AP)",
                              f"{lab} expected" if m != "total" else "Total expected")
            h2[va], h2[ve] = (f"{lab} votes" if m != "total" else "Total votes (AP)",
                              f"{lab} expected" if m != "total" else "Total expected")
        else:
            h2[sa], h2[se], h2[sd] = f"{lab} actual", f"{lab} expected", f"{lab} diff"
            h2[va], h2[ve], h2[vp] = f"{lab} votes", f"{lab} expected", f"{lab} % of exp"
        kinds.update({sa: "share", se: "share", sd: "diff", va: "votes", ve: "votes", vp: "pctx"})
        for k, nm in enumerate(("actual Dem", "actual GOP", "expected Dem", "expected GOP")):
            h2[hs + k] = f"helper: {m} {nm}"
    h2[SOURCE_COL] = "Method source"
    return h1, h2, kinds


def county_row(r: int, fips, name) -> list:
    row = [""] * NCOLS
    row[0], row[1], row[2] = f"=vlookup(B{r},grouping!A:C,3,false)", fips, name
    for m, (_, src, ap, ep, (sa, se, sd), (va, ve, vp), hs) in METHODS.items():
        act = M if src == "M" else A
        row[sa] = "=" + act(ap + "two_way", r)
        row[se] = "=" + A(ep + "two_way", r)
        row[sd] = f'=IF(OR({L(sa)}{r}="",{L(se)}{r}=""),"",{L(sa)}{r}-{L(se)}{r})'
        row[va] = "=" + act(ap + "total_votes", r)
        row[ve] = "=" + A(ep + "total_votes", r)
        row[vp] = f'=IF(OR({L(va)}{r}="",{L(ve)}{r}="",{L(ve)}{r}=0),"",{L(va)}{r}/{L(ve)}{r})'
        row[hs] = "=" + act(ap + "dem_votes", r)
        row[hs + 1] = "=" + act(ap + "gop_votes", r)
        row[hs + 2] = "=" + A(ep + "dem_votes", r)
        row[hs + 3] = "=" + A(ep + "gop_votes", r)
    row[SOURCE_COL] = "=" + M("method_source", r)
    return row


def group_row(r: int, label: str) -> list:
    grp = f'$A${FIRST}:$A${LAST}<>""' if label == "FINAL" else f"$A${FIRST}:$A${LAST}=$C{r}"

    def S(col: int, mask: int) -> str:  # sum of a column over this group's counties where `mask` is filled
        c, k = L(col), L(mask)
        return f'SUM(FILTER({c}${FIRST}:{c}${LAST}, {grp}, {k}${FIRST}:{k}${LAST}<>""))'

    def share(dem: int, gop: int, mask: int) -> str:
        return f"{S(dem, mask)}/({S(dem, mask)}+{S(gop, mask)})"

    row = [""] * NCOLS
    row[2] = label
    for m, (_, _, _, _, (sa, se, sd), (va, ve, vp), hs) in METHODS.items():
        act, exp = share(hs, hs + 1, sd), share(hs + 2, hs + 3, sd)
        row[sa] = f'=IFERROR({act},"")'
        row[se] = f'=IFERROR({exp},"")'
        row[sd] = f'=IFERROR(({act})-({exp}),"")'
        row[va] = f'=IFERROR({S(va, vp)},"")'
        row[ve] = f'=IFERROR({S(ve, vp)},"")'
        row[vp] = f'=IFERROR({S(va, vp)}/{S(ve, vp)},"")'
    crit = '"?*"' if label == "FINAL" else f"$C{r}"
    src = L(SOURCE_COL)
    row[SOURCE_COL] = (f'=COUNTIFS($A${FIRST}:$A${LAST},{crit},{src}${FIRST}:{src}${LAST},"itemized")'
                       f'&" itemized"')
    return row


def build(sheet_id: str) -> None:
    if sheet_id in PROD_IDS:
        raise SystemExit("Refusing to write to the AP aggregator's production sheet.")
    s, _ = session(KEY)
    api = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    sheets = s.get(api, params={"fields": "sheets(properties,conditionalFormats)"}).json()["sheets"]
    tab = next((x for x in sheets if x["properties"]["title"] == TAB), None)
    if tab is None:
        gid = s.post(api + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}
                     ).json()["replies"][0]["addSheet"]["properties"]["sheetId"]
        ncf = 0
    else:
        gid, ncf = tab["properties"]["sheetId"], len(tab.get("conditionalFormats", []))

    vals = s.get(f"{api}/values/Topline!B13:C100").json()["values"]
    counties = [(int(f), n) for f, n in vals]
    assert len(counties) == LAST - FIRST + 1, len(counties)

    h1, h2, kinds = headers()
    rows = [h1, h2] + [group_row(3 + i, g) for i, g in enumerate(GROUPS)] + [[""] * NCOLS, h1, h2]
    rows += [county_row(FIRST + i, f, n) for i, (f, n) in enumerate(counties)]
    nrows = len(rows)

    req = [{"deleteConditionalFormatRule": {"sheetId": gid, "index": 0}} for _ in range(ncf)]
    req += [
        {"updateCells": {"range": {"sheetId": gid}, "fields": "userEnteredValue,userEnteredFormat"}},
        {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {
            "rowCount": nrows, "columnCount": NCOLS, "frozenRowCount": 3, "frozenColumnCount": 3}},
            "fields": "gridProperties(rowCount,columnCount,frozenRowCount,frozenColumnCount)"}},
        {"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 0,
                                                 "endIndex": NCOLS},
                                       "properties": {"hiddenByUser": False}, "fields": "hiddenByUser"}},
    ]
    s.post(api + ":batchUpdate", json={"requests": req}).raise_for_status()
    s.put(f"{api}/values/{TAB}!A1", params={"valueInputOption": "USER_ENTERED"},
          json={"values": rows}).raise_for_status()

    pats = {"diff": ("+0.0%;-0.0%;0.0%", "PERCENT"), "pctx": ("0%", "PERCENT"),
            "share": ("0.0%", "PERCENT"), "votes": ("#,##0", "NUMBER")}

    def rng(r0, r1, c0, c1):
        return {"sheetId": gid, "startRowIndex": r0, "endRowIndex": r1, "startColumnIndex": c0, "endColumnIndex": c1}

    bold = {"userEnteredFormat": {"textFormat": {"bold": True}, "wrapStrategy": "WRAP"}}
    req = [{"repeatCell": {"range": rng(r0, r1, 0, NCOLS), "cell": bold,
                           "fields": "userEnteredFormat(textFormat,wrapStrategy)"}} for r0, r1 in ((0, 6), (7, 9))]
    req.append({"repeatCell": {"range": rng(9, nrows, 3, 9),
                               "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                               "fields": "userEnteredFormat.textFormat.bold"}})
    for c, k in kinds.items():
        p, t = pats[k]
        req.append({"repeatCell": {"range": rng(2, nrows, c, c + 1),
                                   "cell": {"userEnteredFormat": {"numberFormat": {"type": t, "pattern": p}}},
                                   "fields": "userEnteredFormat.numberFormat"}})
        if k == "diff":
            req.append({"addConditionalFormatRule": {"index": 0, "rule": {
                "ranges": [rng(2, 6, c, c + 1), rng(FIRST - 1, nrows, c, c + 1)],
                "gradientRule": {
                    "minpoint": {"color": {"red": 0.90, "green": 0.49, "blue": 0.45}, "type": "NUMBER", "value": "-0.05"},
                    "midpoint": {"color": {"red": 1, "green": 1, "blue": 1}, "type": "NUMBER", "value": "0"},
                    "maxpoint": {"color": {"red": 0.45, "green": 0.62, "blue": 0.90}, "type": "NUMBER", "value": "0.05"}}}}})
    for c in (3, 6, 9, 15, 21, 27, SOURCE_COL):
        req.append({"updateBorders": {"range": rng(0, nrows, c, c + 1), "left": {"style": "SOLID_MEDIUM"}}})
    req.append({"updateBorders": {"range": rng(5, 6, 0, SOURCE_COL + 1), "bottom": {"style": "SOLID_MEDIUM"}}})
    # group colours, shared with the charts and Topline (tools/sheet_palette.py)
    # county names (column C) by the group in column A, which the owner keeps hidden
    req += group_shading_rules(gid, [(3, 6, 2, 3), (FIRST - 1, nrows, 2, 3, "A")])
    req.append({"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS",
                                                        "startIndex": SOURCE_COL + 1, "endIndex": NCOLS},
                                              "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}})
    s.post(api + ":batchUpdate", json={"requests": req}).raise_for_status()
    print(f"validations: {len(counties)} counties + {len(GROUPS)} group rows, "
          f"{NCOLS - SOURCE_COL - 1} hidden helper columns -> {sheet_id}")


def main(argv=None) -> int:
    sheet_id = os.environ.get("GSHEET_ID")
    if not sheet_id:
        print("Set GSHEET_ID", file=sys.stderr)
        return 2
    build(sheet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
