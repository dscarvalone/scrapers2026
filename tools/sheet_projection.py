"""Build the 'projection' tab of the owner's election-night Google Sheet.

Laid out like the owner's earlier model: a Mail block and an Eday block, one
row per group (base / swing / rurals) plus a total, with columns
    votes in | Dem in | Rep in | expected votes | % of expected in |
    Dem % | Rep % | margin | outstanding | Dem outstanding | Rep outstanding |
    margin change
then a projected-margin rollup and the county detail the blocks are built from.

Method (the post-election playbook):
  a) Eday: a county is "done" when Eday votes counted >= cutoff (B2, default
     90%) x the model's expected Eday votes; done counties have 0 outstanding.
  b/c) counties grouped by done status and by group.
  d) Eday outstanding = sum over not-done counties of max(0, expected - counted);
     split at the group's current Eday Dem % / Rep %. A group with no Eday
     votes counted yet gets no split (blank, "not projected"): no model shares.
  e) Mail outstanding = max(0, expected - counted) per county, at the group's
     current mail Dem % / Rep %, or at the Brown 2-way assumption typed in
     column N (an input, kept on rebuild).
Dem % / Rep % are shares of all votes (minor candidates included), as in the
owner's sheet.

No imputation: a county with no Eday count (no split and no first-drop
estimate) is left out of the Eday block, expected votes included, and the
block shows how much of the expected vote that leaves out. The Mail block uses
only counties that report mail separately. Early in-person votes are counted
before Election Day, so they need no outstanding estimate.

Reads 'validations', so it updates with the data. Writes only this tab.
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
V = "validations"

CUTOFF = "$B$2"
MAIL_H, MAIL0 = 4, 5        # mail block: header row 4, groups 5-7, total 8
EDAY_H, EDAY0 = 11, 12      # eday block: header row 11, groups 12-14, total 15
PROJ_H, PROJ0 = 18, 19      # projection: header row 18, groups 19-21, total 22
DET_H, C0 = 25, 26          # county detail: header row 25, counties 26..
C1 = C0 + N - 1
NCOLS = 17

BLOCK_COLS = ["votes in", "Dem in", "Rep in", "expected votes", "% of expected in", "Dem %", "Rep %",
              "Margin", "Outstanding", "Dem outstanding", "Rep outstanding", "Margin change"]

# county detail columns
DET = ["Group", "FIPS", "County", "Eday votes in", "Dem Eday", "Rep Eday", "Expected Eday votes",
       "% of expected Eday", "Status", "Eday outstanding", "Mail votes in", "Dem mail", "Rep mail",
       "Mail expected votes", "Mail outstanding", "Current margin (AP)", "Expected total votes"]


def rng_(col: str) -> str:
    return f"${col}${C0}:${col}${C1}"


def county_row(r: int, v: int) -> list:
    return [
        f"={V}!A{v}", f"={V}!B{v}", f"={V}!C{v}",
        f'=IF({V}!P{v}="","",{V}!P{v})',                                       # D Eday in
        f'=IF(D{r}="","",N({V}!AI{v}))',                                       # E Dem Eday
        f'=IF(D{r}="","",N({V}!AJ{v}))',                                       # F Rep Eday
        f'=IF({V}!Q{v}="","",{V}!Q{v})',                                       # G expected Eday
        f'=IF(OR(D{r}="",G{r}="",N(G{r})=0),"",D{r}/G{r})',                    # H % of expected
        f'=IF(H{r}="","no Eday count",IF(H{r}>={CUTOFF},"done","not done"))',  # I status
        f'=IF(I{r}="no Eday count","",IF(I{r}="done",0,MAX(0,G{r}-D{r})))',    # J Eday outstanding
        f'=IF({V}!AE{v}="","",{V}!AE{v})',                                     # K mail in
        f'=IF(K{r}="","",N({V}!AY{v}))',                                       # L Dem mail
        f'=IF(K{r}="","",N({V}!AZ{v}))',                                       # M Rep mail
        f'=IF(K{r}="","",N({V}!AF{v}))',                                       # N mail expected
        f'=IF(K{r}="","",MAX(0,N{r}-K{r}))',                                   # O mail outstanding
        f"=N({V}!AQ{v})-N({V}!AR{v})",                                         # P current margin
        f"=N({V}!U{v})",                                                       # Q expected total
    ]


def S(col: str, r: int, extra: str = "") -> str:
    return f"SUMIFS({rng_(col)},{rng_('A')},$A{r}{extra})"


def eday_row(r: int) -> list:
    counted = f',{rng_("I")},"<>no Eday count"'
    return [
        None,
        f"={S('D', r)}", f"={S('E', r)}", f"={S('F', r)}",
        f"={S('G', r, counted)}",
        f'=IFERROR(B{r}/E{r},"")',
        f'=IF(B{r}>0,C{r}/B{r},"")',
        f'=IF(B{r}>0,D{r}/B{r},"")',
        f'=IF(G{r}="","",G{r}-H{r})',
        f"={S('J', r)}",
        f'=IF(G{r}="","",J{r}*G{r})', f'=IF(H{r}="","",J{r}*H{r})',
        f'=IF(K{r}="","",K{r}-L{r})',
        f'=IF(B{r}>0,"counted Eday","no Eday votes yet: not projected")',
        f'=COUNTIFS({rng_("A")},$A{r},{rng_("I")},"done")&" done / "&COUNTIFS({rng_("A")},$A{r},{rng_("I")},'
        f'"not done")&" not done / "&COUNTIFS({rng_("A")},$A{r},{rng_("I")},"no Eday count")&" no count"',
        f'=IFERROR(1-{S("Q", r, counted)}/{S("Q", r)},"")',
    ]


def mail_row(r: int, kept_input) -> list:
    a = f"N{r}"
    return [
        None,
        f"={S('K', r)}", f"={S('L', r)}", f"={S('M', r)}", f"={S('N', r)}",
        f'=IFERROR(B{r}/E{r},"")',
        f'=IF(B{r}>0,C{r}/B{r},"")', f'=IF(B{r}>0,D{r}/B{r},"")',
        f'=IF(G{r}="","",G{r}-H{r})',
        f"={S('O', r)}",
        f'=IF({a}<>"",J{r}*IF(G{r}="",1,G{r}+H{r})*{a},IF(G{r}="","",J{r}*G{r}))',
        f'=IF({a}<>"",J{r}*IF(G{r}="",1,G{r}+H{r})*(1-{a}),IF(H{r}="","",J{r}*H{r}))',
        f'=IF(K{r}="","",K{r}-L{r})',
        kept_input,
        f'=SUMPRODUCT(({rng_("A")}=$A{r})*({rng_("K")}<>""))&" of "&COUNTIF({rng_("A")},$A{r})&" counties"',
    ]


def total_row(r: int, first: int, eday: bool) -> list:
    last = first + 2
    sm = lambda c: f"=SUM({c}{first}:{c}{last})"
    row = [None, sm("B"), sm("C"), sm("D"), sm("E"), f'=IFERROR(B{r}/E{r},"")',
           f'=IFERROR(C{r}/B{r},"")', f'=IFERROR(D{r}/B{r},"")', f'=IF(G{r}="","",G{r}-H{r})',
           sm("J"), sm("K"), sm("L"), sm("M")]
    if eday:
        row += ["",
                f'=COUNTIF({rng_("I")},"done")&" done / "&COUNTIF({rng_("I")},"not done")&" not done / "'
                f'&COUNTIF({rng_("I")},"no Eday count")&" no count"',
                f'=IFERROR(1-SUMIFS({rng_("Q")},{rng_("I")},"<>no Eday count")/SUM({rng_("Q")}),"")']
    else:
        row += ["", f'=COUNT({rng_("K")})&" of {N} counties"']
    return row


def build(sheet_id: str) -> None:
    if sheet_id in PROD_IDS:
        raise SystemExit("Refusing to write to the AP aggregator's production sheet.")
    s, _ = session(KEY)
    api = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    sheets = s.get(api, params={"fields": "sheets(properties,conditionalFormats)"}).json()["sheets"]
    tab = next((x for x in sheets if x["properties"]["title"] == TAB), None)
    cutoff, mail_in = 0.9, {}
    if tab is None:
        gid = s.post(api + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}
                     ).json()["replies"][0]["addSheet"]["properties"]["sheetId"]
        ncf = 0
    else:
        gid, ncf = tab["properties"]["sheetId"], len(tab.get("conditionalFormats", []))
        cur = s.get(f"{api}/values/{TAB}!A1:N{MAIL0 + 2}", params={"valueRenderOption": "UNFORMATTED_VALUE"}
                    ).json().get("values", [])
        cur = [r + [""] * (14 - len(r)) for r in cur]
        if len(cur) >= 2 and isinstance(cur[1][1], (int, float)):
            cutoff = cur[1][1]
        for i in range(3):  # Brown 2-way assumption inputs (only if this layout's header is there)
            if len(cur) > MAIL0 - 1 + i and len(cur) >= MAIL_H and "assumption" in str(cur[MAIL_H - 1][13]):
                val = cur[MAIL0 - 1 + i][13]
                if isinstance(val, (int, float)):
                    mail_in[i] = val

    rows = [[""] * NCOLS for _ in range(C1)]
    rows[0][0] = "E-night projection (formulas; updates with the data)"
    rows[1][0:3] = ["Eday done cutoff", cutoff,
                    "<- input: a county with Eday votes counted at or above this share of its expected Eday "
                    "votes is done (0 outstanding)."]
    rows[MAIL_H - 1] = ["Mail"] + ["Mail " + c if i in (0, 3) else c.replace("in", "mail in") if i in (1, 2)
                                   else c for i, c in enumerate(BLOCK_COLS)] + \
        ["Brown 2-way assumption (optional input)", "Counties reporting mail", "", "", "", ""]
    for i, g in enumerate(GROUPS):
        r = MAIL0 + i
        rows[r - 1] = mail_row(r, mail_in.get(i, "")) + [""] * 4
        rows[r - 1][0] = g
    rows[MAIL0 + 2] = total_row(MAIL0 + 3, MAIL0, False) + [""] * 5
    rows[MAIL0 + 2][0] = "Total"
    rows[MAIL0 + 3][0] = ("Mail: only counties that report mail separately. Outstanding = expected minus counted "
                          "(0 if over). With an assumption in column N, outstanding mail is split at that Brown "
                          "2-way share instead of the current mail shares.")

    rows[EDAY_H - 1] = ["Eday"] + ["Eday " + c if i in (0, 3) else c.replace("in", "Eday in") if i in (1, 2)
                                   else c for i, c in enumerate(BLOCK_COLS)] + \
        ["Share from", "Counties", "Expected vote not covered", "", "", ""]
    for i, g in enumerate(GROUPS):
        r = EDAY0 + i
        rows[r - 1] = eday_row(r) + [""] * 3
        rows[r - 1][0] = g
    rows[EDAY0 + 2] = total_row(EDAY0 + 3, EDAY0, True) + [""] * 3
    rows[EDAY0 + 2][0] = "Total"
    rows[EDAY0 + 3][0] = ("Eday: counties with an Eday count only (itemized or first drop); others are left out, "
                          "expected votes included, and counted under 'Expected vote not covered'. "
                          "Done counties have 0 outstanding.")

    rows[PROJ_H - 1][0:6] = ["Projected margin", "Current margin (AP)", "Eday margin change",
                             "Mail margin change", "Projected margin", "Expected vote without an Eday count"]
    for i, g in enumerate(GROUPS):
        r = PROJ0 + i
        rows[r - 1][0:6] = [g, f"={S('P', r)}", f"=N(M{EDAY0 + i})", f"=N(M{MAIL0 + i})",
                            f"=B{r}+C{r}+D{r}", f"=P{EDAY0 + i}"]
    t = PROJ0 + 3
    rows[t - 1][0:6] = ["Total", f"=SUM(B{PROJ0}:B{t - 1})", f"=SUM(C{PROJ0}:C{t - 1})",
                        f"=SUM(D{PROJ0}:D{t - 1})", f"=B{t}+C{t}+D{t}", f"=P{EDAY0 + 3}"]

    rows[DET_H - 1] = DET
    for k in range(N):
        rows[C0 - 1 + k] = county_row(C0 + k, FIRST + k)

    req = [{"deleteConditionalFormatRule": {"sheetId": gid, "index": 0}} for _ in range(ncf)]
    req += [{"updateCells": {"range": {"sheetId": gid}, "fields": "userEnteredValue,userEnteredFormat"}},
            {"unmergeCells": {"range": {"sheetId": gid}}},
            {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {
                "rowCount": C1, "columnCount": NCOLS, "frozenRowCount": 0, "frozenColumnCount": 1}},
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

    def cell(r0, r1, c0, c1, fmt_, fields):
        return {"repeatCell": {"range": rng(r0, r1, c0, c1), "cell": {"userEnteredFormat": fmt_}, "fields": fields}}

    hdr = {"textFormat": {"bold": True}, "wrapStrategy": "WRAP", "verticalAlignment": "BOTTOM",
           "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}}
    hdr_f = "userEnteredFormat(textFormat,wrapStrategy,verticalAlignment,backgroundColor)"
    input_bg = {"backgroundColor": {"red": 1, "green": 0.95, "blue": 0.8}}
    margin = "+#,##0;-#,##0;0"
    pts = "+0.0%;-0.0%;0.0%"
    req = [cell(0, 1, 0, 1, {"textFormat": {"bold": True, "fontSize": 12}}, "userEnteredFormat.textFormat"),
           cell(1, 2, 0, 1, {"textFormat": {"bold": True}}, "userEnteredFormat.textFormat"),
           fmt(1, 2, 1, 2, "0%", "PERCENT"), cell(1, 2, 1, 2, input_bg, "userEnteredFormat.backgroundColor")]
    for h, first, extra in ((MAIL_H, MAIL0, 2), (EDAY_H, EDAY0, 3)):
        r0, r1 = first - 1, first + 3  # 3 groups + total
        req += [cell(h - 1, h, 0, 13 + extra, hdr, hdr_f),
                fmt(r0, r1, 1, 5, "#,##0"), fmt(r0, r1, 5, 8, "0.0%", "PERCENT"), fmt(r0, r1, 8, 9, pts, "PERCENT"),
                fmt(r0, r1, 9, 12, "#,##0"), fmt(r0, r1, 12, 13, margin),
                cell(r1 - 1, r1, 0, 13 + extra, {"textFormat": {"bold": True}}, "userEnteredFormat.textFormat"),
                {"updateBorders": {"range": rng(r1 - 1, r1, 0, 13 + extra), "top": {"style": "SOLID"}}},
                cell(r1, r1 + 1, 0, 1, {"textFormat": {"italic": True, "foregroundColor":
                                         {"red": 0.4, "green": 0.4, "blue": 0.4}}}, "userEnteredFormat.textFormat")]
    req += [fmt(MAIL0 - 1, MAIL0 + 2, 13, 14, "0.0%", "PERCENT"),
            cell(MAIL0 - 1, MAIL0 + 2, 13, 14, input_bg, "userEnteredFormat.backgroundColor"),
            fmt(EDAY0 - 1, EDAY0 + 3, 15, 16, "0%", "PERCENT"),
            cell(PROJ_H - 1, PROJ_H, 0, 6, hdr, hdr_f),
            fmt(PROJ0 - 1, PROJ0 + 3, 1, 5, margin), fmt(PROJ0 - 1, PROJ0 + 3, 5, 6, "0%", "PERCENT"),
            cell(PROJ0 + 2, PROJ0 + 3, 0, 6, {"textFormat": {"bold": True}}, "userEnteredFormat.textFormat"),
            {"updateBorders": {"range": rng(PROJ0 + 2, PROJ0 + 3, 0, 6), "top": {"style": "SOLID"}}},
            cell(PROJ0 - 1, PROJ0 + 3, 4, 5, {"textFormat": {"bold": True}}, "userEnteredFormat.textFormat"),
            cell(DET_H - 1, DET_H, 0, NCOLS, hdr, hdr_f),
            fmt(C0 - 1, C1, 3, 7, "#,##0"), fmt(C0 - 1, C1, 7, 8, "0%", "PERCENT"),
            fmt(C0 - 1, C1, 9, 15, "#,##0"), fmt(C0 - 1, C1, 15, 16, margin), fmt(C0 - 1, C1, 16, 17, "#,##0"),
            {"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 0,
                                                     "endIndex": 1}, "properties": {"pixelSize": 150},
                                           "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 1,
                                                     "endIndex": NCOLS}, "properties": {"pixelSize": 105},
                                           "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 14,
                                                     "endIndex": 15}, "properties": {"pixelSize": 230},
                                           "fields": "pixelSize"}}]
    for status, col in (("done", {"red": 0.72, "green": 0.88, "blue": 0.8}),
                        ("not done", {"red": 1, "green": 0.9, "blue": 0.6}),
                        ("no Eday count", {"red": 0.85, "green": 0.85, "blue": 0.85})):
        req.append({"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [rng(C0 - 1, C1, 8, 9)],
            "booleanRule": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": status}]},
                            "format": {"backgroundColor": col}}}}})
    req += group_shading_rules(gid, [(MAIL0 - 1, MAIL0 + 2, 0, 1), (EDAY0 - 1, EDAY0 + 2, 0, 1),
                                     (PROJ0 - 1, PROJ0 + 2, 0, 1), (C0 - 1, C1, 2, 3, "A")])
    r = s.post(api + ":batchUpdate", json={"requests": req})
    if r.status_code != 200:
        raise SystemExit(f"Format request failed: {r.status_code} {r.text[:400]}")
    print(f"projection: mail + Eday blocks, cutoff {cutoff}, mail assumptions kept {mail_in} -> {sheet_id}")


def main(argv=None) -> int:
    sheet_id = os.environ.get("GSHEET_ID")
    if not sheet_id:
        print("Set GSHEET_ID", file=sys.stderr)
        return 2
    build(sheet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
