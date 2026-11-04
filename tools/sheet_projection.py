"""Build the 'projection' tab of the owner's election-night Google Sheet.

A projection that doesn't need complete results-by-mode. Every county takes
one of three paths, decided by what it reports (all formulas, reading
'validations' and 'methods', so it updates with the data):

  Eday count   the county has an Election Day number: itemized by its own feed,
               or read from the SOS totals (first drop = pre-Election-Day,
               growth since = Election Day). Done when Eday votes counted >=
               cutoff (B2) x the model's expected Eday votes. Not done:
               outstanding = expected Eday - counted, at the county's own Eday
               share "so far" or of its "latest batch" (B3).
  totals only  votes but no Eday split (its first report already mixed early
               and Election Day). Never marked done: its count can't be split
               into Early (a known ballot count) and Eday, so any shortfall may
               be Early ballots. Outstanding = expected total - counted, at the
               county's latest-batch share (the votes added by its last change
               in the SOS totals: what is coming in now); its current total
               share if there is no batch.
  no votes     nothing counted: not projected (no share to apply); the
               summary shows how much expected vote that leaves out.

Counted votes, batches and the current margin all come from our feed (the
'methods' tab: county feeds + SOS totals), so they are one consistent source;
the model ('dscc data tab', via 'validations') supplies only expected votes.
Shares are each county's own (Dem % / Rep % of all its votes, minor
candidates included); nothing is borrowed from other counties, no history,
no regression. "Done" uses closeness to the model's expected votes, not
precincts reporting.

Early block: every county NOT on the totals-only path (pre-results: all 88).
The model's expected Early is the literal count of early ballots submitted
(in-person early + mail; known), so outstanding = expected Early - counted,
with no done cutoff. Dem/Rep outstanding are county by county at the county's
own Early share; a county with no Early votes counted yet has its outstanding
Early counted but not projected (column P), unless a Brown 2-way assumption is
typed in column N, which then applies to the group's whole outstanding Early.
Totals-only counties' Early ballots are inside their totals outstanding, so
nothing is counted twice.

Layout: inputs; then Eday, Totals-only and Early blocks by group (votes in |
Dem in | Rep in | expected | % of expected in | Dem % | Rep % | margin |
outstanding | Dem outstanding | Rep outstanding | margin change); then the
projected margin; then the county detail.
Inputs (B2, B3, Early column N) are kept on rebuild.
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
M = "methods"

CUTOFF, BASIS = "$B$2", "$B$3"
EDAY_H, EDAY0 = 6, 7        # Eday block: header 6, groups 7-9, total 10, note 11
TOT_H, TOT0 = 14, 15        # Totals-only block: header 14, groups 15-17, total 18, note 19
EARLY_H, EARLY0 = 22, 23    # Early block: header 22, groups 23-25, total 26, note 27
PROJ_H, PROJ0 = 30, 31      # projected margin: header 30, groups 31-33, total 34
DET_H, C0 = 37, 38          # county detail
C1 = C0 + N - 1
NCOLS = 37

BLOCK_COLS = ["votes in", "Dem in", "Rep in", "expected votes", "% of expected in", "Dem %", "Rep %",
              "Margin", "Outstanding", "Dem outstanding", "Rep outstanding", "Margin change"]

DET = ["Group", "FIPS", "County", "Path",
       "Eday votes in", "Dem Eday", "Rep Eday", "Expected Eday", "% of exp. Eday", "Eday status",
       "Eday outstanding", "Eday out Dem", "Eday out Rep",
       "Total votes in", "Dem total", "Rep total", "Expected total", "% of exp. total", "Totals status",
       "Totals outstanding", "Totals out Dem", "Totals out Rep",
       "Early votes in", "Dem Early", "Rep Early", "Expected Early", "Early outstanding",
       "Early out Dem", "Early out Rep", "Early out not projected",
       "Batch Dem", "Batch Rep", "Batch total", "Batch as of", "Share used",
       "Current margin", "Expected total (coverage)"]
COL = {name: i for i, name in enumerate(DET)}


def L(i: int) -> str:
    s, i = "", i + 1
    while i:
        i, rm = divmod(i - 1, 26)
        s = chr(65 + rm) + s
    return s


def c_(name: str) -> str:
    return L(COL[name])


def rng_(name: str) -> str:
    c = c_(name)
    return f"${c}${C0}:${c}${C1}"


def mlook(field: str, r: int) -> str:
    """value of a methods-tab field for this row's county (blank if missing)."""
    return f'IFERROR(VLOOKUP($C{r},{M}!$C$1:$ZZ$999,MATCH("{field}",{M}!$1:$1,0)-2,FALSE),"")'


def county_row(r: int, v: int) -> list:
    k = {n: f"{c_(n)}{r}" for n in DET}
    eday_dem = f'IF(AND({BASIS}="latest batch",N({k["Batch total"]})>0),{k["Batch Dem"]}/{k["Batch total"]},' \
               f'IF(N({k["Eday votes in"]})>0,{k["Dem Eday"]}/{k["Eday votes in"]},""))'
    eday_rep = f'IF(AND({BASIS}="latest batch",N({k["Batch total"]})>0),{k["Batch Rep"]}/{k["Batch total"]},' \
               f'IF(N({k["Eday votes in"]})>0,{k["Rep Eday"]}/{k["Eday votes in"]},""))'
    tot_dem = f'IF(N({k["Batch total"]})>0,{k["Batch Dem"]}/{k["Batch total"]},' \
              f'IF(N({k["Total votes in"]})>0,{k["Dem total"]}/{k["Total votes in"]},""))'
    tot_rep = f'IF(N({k["Batch total"]})>0,{k["Batch Rep"]}/{k["Batch total"]},' \
              f'IF(N({k["Total votes in"]})>0,{k["Rep total"]}/{k["Total votes in"]},""))'
    eday = f'{k["Path"]}="Eday count"'
    tot = f'{k["Path"]}="totals only"'
    row = {
        "Group": f"={V}!A{v}", "FIPS": f"={V}!B{v}", "County": f"={V}!C{v}",
        "Path": f'=IF(N({mlook("total_votes", r)})=0,"no votes",IF({V}!P{v}<>"","Eday count","totals only"))',
        "Eday votes in": f'=IF({eday},N({V}!P{v}),"")',
        "Dem Eday": f'=IF({eday},N({V}!AI{v}),"")',
        "Rep Eday": f'=IF({eday},N({V}!AJ{v}),"")',
        "Expected Eday": f'=IF({eday},N({V}!Q{v}),"")',
        "% of exp. Eday": f'=IF(AND({eday},N({k["Expected Eday"]})>0),{k["Eday votes in"]}/{k["Expected Eday"]},"")',
        "Eday status": f'=IF({k["% of exp. Eday"]}="","",IF({k["% of exp. Eday"]}>={CUTOFF},"done","not done"))',
        "Eday outstanding": f'=IF({eday},IF({k["Eday status"]}="done",0,MAX(0,{k["Expected Eday"]}-{k["Eday votes in"]})),"")',
        "Eday out Dem": f'=IF({k["Eday outstanding"]}="","",IFERROR({k["Eday outstanding"]}*{eday_dem},""))',
        "Eday out Rep": f'=IF({k["Eday outstanding"]}="","",IFERROR({k["Eday outstanding"]}*{eday_rep},""))',
        "Total votes in": f"=N({mlook('total_votes', r)})",
        "Dem total": f"=N({mlook('dem_votes', r)})", "Rep total": f"=N({mlook('gop_votes', r)})",
        "Expected total": f'=IF({tot},N({V}!U{v}),"")',
        "% of exp. total": f'=IF(AND({tot},N({k["Expected total"]})>0),{k["Total votes in"]}/{k["Expected total"]},"")',
        "Totals status": f'=IF({tot},"open","")',  # never marked done: Eday/Early mix unknown
        # never done: the counted votes can't be split into Early (a known ballot count) and Eday,
        # so a shortfall against expected may be Early ballots still to count
        "Totals outstanding": f'=IF({tot},MAX(0,{k["Expected total"]}-{k["Total votes in"]}),"")',
        "Totals out Dem": f'=IF({k["Totals outstanding"]}="","",IFERROR({k["Totals outstanding"]}*{tot_dem},""))',
        "Totals out Rep": f'=IF({k["Totals outstanding"]}="","",IFERROR({k["Totals outstanding"]}*{tot_rep},""))',
        "Early votes in": f'=IF({tot},"",N({V}!R{v}))',
        "Dem Early": f'=IF({k["Early votes in"]}="","",N({V}!AM{v}))',
        "Rep Early": f'=IF({k["Early votes in"]}="","",N({V}!AN{v}))',
        "Expected Early": f'=IF({k["Early votes in"]}="","",N({V}!S{v}))',
        "Early outstanding": f'=IF({k["Early votes in"]}="","",MAX(0,{k["Expected Early"]}-{k["Early votes in"]}))',
        "Early out Dem": f'=IF(OR({k["Early outstanding"]}="",N({k["Early votes in"]})=0),"",'
                         f'{k["Early outstanding"]}*{k["Dem Early"]}/{k["Early votes in"]})',
        "Early out Rep": f'=IF(OR({k["Early outstanding"]}="",N({k["Early votes in"]})=0),"",'
                         f'{k["Early outstanding"]}*{k["Rep Early"]}/{k["Early votes in"]})',
        "Early out not projected": f'=IF({k["Early outstanding"]}="","",IF(N({k["Early votes in"]})>0,0,'
                                   f'{k["Early outstanding"]}))',
        "Batch Dem": f"={mlook('batch_dem_votes', r)}",
        "Batch Rep": f"={mlook('batch_gop_votes', r)}",
        "Batch total": f"={mlook('batch_total_votes', r)}",
        "Batch as of": f"={mlook('batch_as_of', r)}",
        "Share used": f'=IF({eday},IF(AND({BASIS}="latest batch",N({k["Batch total"]})>0),"Eday: latest batch",'
                      f'IF(N({k["Eday votes in"]})>0,"Eday so far","no Eday votes yet")),'
                      f'IF({tot},IF(N({k["Batch total"]})>0,"latest batch","current total"),"not projected"))',
        "Current margin": f'={k["Dem total"]}-{k["Rep total"]}',
        "Expected total (coverage)": f'=N({V}!U{v})',
    }
    return [row[n] for n in DET]


def S(name: str, r: int, extra: str = "") -> str:
    return f"SUMIFS({rng_(name)},{rng_('Group')},$A{r}{extra})"


def block_row(r: int, kind: str, assumption=None) -> list:
    """One group row of a block. kind: eday / totals / early."""
    if kind == "eday":
        vin, din, rin, exp, out, dout, rout = ("Eday votes in", "Dem Eday", "Rep Eday", "Expected Eday",
                                               "Eday outstanding", "Eday out Dem", "Eday out Rep")
        path = f',{rng_("Path")},"Eday count"'
    elif kind == "totals":
        vin, din, rin, exp, out, dout, rout = ("Total votes in", "Dem total", "Rep total", "Expected total",
                                               "Totals outstanding", "Totals out Dem", "Totals out Rep")
        path = f',{rng_("Path")},"totals only"'
    else:
        vin, din, rin, exp, out = ("Early votes in", "Dem Early", "Rep Early", "Expected Early", "Early outstanding")
        path = ""
    row = [None, f"={S(vin, r, path)}", f"={S(din, r, path)}", f"={S(rin, r, path)}", f"={S(exp, r, path)}",
           f'=IFERROR(B{r}/E{r},"")', f'=IF(B{r}>0,C{r}/B{r},"")', f'=IF(B{r}>0,D{r}/B{r},"")',
           f'=IF(G{r}="","",G{r}-H{r})', f"={S(out, r, path)}"]
    if kind == "early":
        a = f"N{r}"
        row += [f'=IF({a}<>"",J{r}*IF(G{r}="",1,G{r}+H{r})*{a},{S("Early out Dem", r)})',
                f'=IF({a}<>"",J{r}*IF(G{r}="",1,G{r}+H{r})*(1-{a}),{S("Early out Rep", r)})',
                f"=K{r}-L{r}", assumption if assumption is not None else "",
                f'=COUNTIFS({rng_("Group")},$A{r},{rng_("Early votes in")},">0")&" of "'
                f'&COUNTIFS({rng_("Group")},$A{r},{rng_("Path")},"<>totals only")&" counties with Early votes counted"',
                f'=IF({a}<>"",0,{S("Early out not projected", r)})']
    else:
        st = "Eday status" if kind == "eday" else "Totals status"
        pv = "Eday count" if kind == "eday" else "totals only"
        cnt = (f'COUNTIFS({rng_("Group")},$A{r},{rng_("Path")},"{pv}")&" counties: "'
               f'&COUNTIFS({rng_("Group")},$A{r},{rng_(st)},"done")&" done / "'
               f'&COUNTIFS({rng_("Group")},$A{r},{rng_(st)},"not done")&" not done"') if kind == "eday" else \
              f'COUNTIFS({rng_("Group")},$A{r},{rng_("Path")},"{pv}")&" counties (never marked done)"'
        row += [f"={S(dout, r, path)}", f"={S(rout, r, path)}", f"=K{r}-L{r}", "=" + cnt]
    return row


def total_row(r: int, first: int, kind: str) -> list:
    last = first + 2
    sm = lambda c: f"=SUM({c}{first}:{c}{last})"
    row = [None, sm("B"), sm("C"), sm("D"), sm("E"), f'=IFERROR(B{r}/E{r},"")', f'=IFERROR(C{r}/B{r},"")',
           f'=IFERROR(D{r}/B{r},"")', f'=IF(G{r}="","",G{r}-H{r})', sm("J"), sm("K"), sm("L"), sm("M")]
    if kind == "early":
        row += ["", f'=COUNTIF({rng_("Early votes in")},">0")&" of "&COUNTIF({rng_("Path")},"<>totals only")'
                    f'&" counties with Early votes counted"', f"=SUM(P{first}:P{last})"]
    else:
        pv = "Eday count" if kind == "eday" else "totals only"
        st = "Eday status" if kind == "eday" else "Totals status"
        row += [f'=COUNTIF({rng_("Path")},"{pv}")&" counties: "&COUNTIF({rng_(st)},"done")&" done / "'
                f'&COUNTIF({rng_(st)},"not done")&" not done"' if kind == "eday" else
                f'=COUNTIF({rng_("Path")},"{pv}")&" counties (never marked done)"']
    return row


def block_header(label: str, kind: str) -> list:
    pre = {"eday": "Eday ", "totals": "", "early": "Early "}[kind]
    cols = [(pre + c if i in (0, 3) else c.replace("in", pre + "in") if i in (1, 2) and pre else c)
            for i, c in enumerate(BLOCK_COLS)]
    tail = (["Brown 2-way assumption for outstanding Early (optional input)", "Counties with Early votes counted",
             "Early outstanding not projected (no Early votes counted yet)"]
            if kind == "early" else ["Counties"])
    return [label] + cols + tail


def build(sheet_id: str) -> None:
    if sheet_id in PROD_IDS:
        raise SystemExit("Refusing to write to the AP aggregator's production sheet.")
    s, _ = session(KEY)
    api = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    sheets = s.get(api, params={"fields": "sheets(properties,conditionalFormats)"}).json()["sheets"]
    tab = next((x for x in sheets if x["properties"]["title"] == TAB), None)
    cutoff, basis, early_in = 0.9, "so far", {}
    if tab is None:
        gid = s.post(api + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}
                     ).json()["replies"][0]["addSheet"]["properties"]["sheetId"]
        ncf = 0
    else:
        gid, ncf = tab["properties"]["sheetId"], len(tab.get("conditionalFormats", []))
        cur = s.get(f"{api}/values/{TAB}!A1:N40", params={"valueRenderOption": "UNFORMATTED_VALUE"}
                    ).json().get("values", [])
        cur = [r + [""] * (14 - len(r)) for r in cur] + [[""] * 14] * 40
        if isinstance(cur[1][1], (int, float)):
            cutoff = cur[1][1]
        if str(cur[2][0]).startswith("Eday share basis") and cur[2][1] in ("so far", "latest batch"):
            basis = cur[2][1]
        # the Early assumption inputs, wherever this layout or the previous one had them
        for h in range(len(cur)):
            if str(cur[h][0]) in ("Early", "Mail") and "assumption" in str(cur[h][13]):
                for i in range(3):
                    val = cur[h + 1 + i][13]
                    if isinstance(val, (int, float)):
                        early_in[i] = val
                break

    rows = [[""] * NCOLS for _ in range(C1)]
    rows[0][0] = "E-night projection (formulas; updates with the data). Every county takes one path: Eday count / " \
                 "totals only / no votes (see column D of the detail)."
    rows[1][0:3] = ["Done cutoff (% of expected)", cutoff,
                    "<- input: an Eday-count county is done (0 Eday outstanding) when its Eday votes counted reach "
                    "this share of the model's expected Eday votes. Totals-only counties are never marked done."]
    rows[2][0:3] = ["Eday share basis", basis,
                    "<- input: 'so far' = each county's Eday share to date; 'latest batch' = the share of the votes "
                    "its last SOS update added. Totals-only counties always use their latest batch."]

    rows[EDAY_H - 1] = block_header("Eday", "eday") + [""] * (NCOLS - 14)
    for i, g in enumerate(GROUPS):
        rows[EDAY0 - 1 + i] = [g] + block_row(EDAY0 + i, "eday")[1:] + [""] * (NCOLS - 14)
    rows[EDAY0 + 2] = ["Total"] + total_row(EDAY0 + 3, EDAY0, "eday")[1:] + [""] * (NCOLS - 14)
    rows[EDAY0 + 3][0] = ("Eday: counties with an Election Day number (itemized, or the SOS first drop). Outstanding "
                          "= expected Eday minus counted, 0 once done, split at each county's own Eday share (B3). "
                          "Dem/Rep outstanding are summed county by county.")

    rows[TOT_H - 1] = block_header("Totals only", "totals") + [""] * (NCOLS - 14)
    for i, g in enumerate(GROUPS):
        rows[TOT0 - 1 + i] = [g] + block_row(TOT0 + i, "totals")[1:] + [""] * (NCOLS - 14)
    rows[TOT0 + 2] = ["Total"] + total_row(TOT0 + 3, TOT0, "totals")[1:] + [""] * (NCOLS - 14)
    rows[TOT0 + 3][0] = ("Totals only: counties with votes but no Eday split. Never marked done (their count can't "
                         "be split into Early, a known ballot count, and Eday): outstanding = expected total minus "
                         "counted, split at each county's latest-batch share (current total share if no batch).")

    rows[EARLY_H - 1] = block_header("Early", "early") + [""] * (NCOLS - 16)
    for i, g in enumerate(GROUPS):
        rows[EARLY0 - 1 + i] = [g] + block_row(EARLY0 + i, "early", early_in.get(i, ""))[1:] + [""] * (NCOLS - 16)
    rows[EARLY0 + 2] = ["Total"] + total_row(EARLY0 + 3, EARLY0, "early")[1:] + [""] * (NCOLS - 16)
    rows[EARLY0 + 3][0] = ("Early = in-person early + mail (a known ballot count), every county not on the "
                           "totals-only path. Outstanding = expected Early minus counted, split at each county's own "
                           "Early share; no share yet = not projected (column P), unless column N has an assumption.")

    rows[PROJ_H - 1][0:7] = ["Projected margin", "Current margin (our feed)", "Eday margin change",
                             "Totals-only margin change", "Early margin change", "Projected margin",
                             "Expected vote not projected (no votes yet)"]
    for i, g in enumerate(GROUPS):
        r = PROJ0 + i
        rows[r - 1][0:7] = [g, f"={S('Current margin', r)}", f"=N(M{EDAY0 + i})", f"=N(M{TOT0 + i})",
                            f"=N(M{EARLY0 + i})", f"=B{r}+C{r}+D{r}+E{r}",
                            f'=IFERROR({S("Expected total (coverage)", r, chr(44) + rng_("Path") + chr(44) + chr(34) + "no votes" + chr(34))}'
                            f'/{S("Expected total (coverage)", r)},"")']
    t = PROJ0 + 3
    cov = rng_("Expected total (coverage)")
    rows[t - 1][0:7] = ["Total", f"=SUM(B{PROJ0}:B{t - 1})", f"=SUM(C{PROJ0}:C{t - 1})", f"=SUM(D{PROJ0}:D{t - 1})",
                        f"=SUM(E{PROJ0}:E{t - 1})", f"=B{t}+C{t}+D{t}+E{t}",
                        f'=IFERROR(SUMIFS({cov},{rng_("Path")},"no votes")/SUM({cov}),"")']

    # Count of done counties, just above the "Eday status" header.
    rows[DET_H - 2][COL["Eday status"]] = f'=COUNTIF({rng_("Eday status")},"done")&" done"'
    rows[DET_H - 1] = DET
    for k in range(N):
        rows[C0 - 1 + k] = county_row(C0 + k, FIRST + k)

    req = [{"deleteConditionalFormatRule": {"sheetId": gid, "index": 0}} for _ in range(ncf)]
    req += [{"updateCells": {"range": {"sheetId": gid}, "fields": "userEnteredValue,userEnteredFormat,dataValidation"}},
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

    def cell(r0, r1, c0, c1, f, fields):
        return {"repeatCell": {"range": rng(r0, r1, c0, c1), "cell": {"userEnteredFormat": f}, "fields": fields}}

    hdr = {"textFormat": {"bold": True}, "wrapStrategy": "WRAP", "verticalAlignment": "BOTTOM",
           "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}}
    hdr_f = "userEnteredFormat(textFormat,wrapStrategy,verticalAlignment,backgroundColor)"
    yellow = {"backgroundColor": {"red": 1, "green": 0.95, "blue": 0.8}}
    margin, pts = "+#,##0;-#,##0;0", "+0.0%;-0.0%;0.0%"
    italic = {"textFormat": {"italic": True, "foregroundColor": {"red": 0.4, "green": 0.4, "blue": 0.4}}}
    req = [cell(0, 1, 0, 1, {"textFormat": {"bold": True, "fontSize": 12}}, "userEnteredFormat.textFormat"),
           cell(1, 3, 0, 1, {"textFormat": {"bold": True}}, "userEnteredFormat.textFormat"),
           fmt(1, 2, 1, 2, "0%", "PERCENT"), cell(1, 3, 1, 2, yellow, "userEnteredFormat.backgroundColor"),
           {"setDataValidation": {"range": rng(2, 3, 1, 2), "rule": {
               "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "so far"},
                                                              {"userEnteredValue": "latest batch"}]},
               "showCustomUi": True, "strict": True}}}]
    for h, first, width in ((EDAY_H, EDAY0, 14), (TOT_H, TOT0, 14), (EARLY_H, EARLY0, 16)):
        r0, r1 = first - 1, first + 3
        req += [cell(h - 1, h, 0, width, hdr, hdr_f),
                fmt(r0, r1, 1, 5, "#,##0"), fmt(r0, r1, 5, 8, "0.0%", "PERCENT"), fmt(r0, r1, 8, 9, pts, "PERCENT"),
                fmt(r0, r1, 9, 12, "#,##0"), fmt(r0, r1, 12, 13, margin),
                cell(r1 - 1, r1, 0, width, {"textFormat": {"bold": True}}, "userEnteredFormat.textFormat"),
                {"updateBorders": {"range": rng(r1 - 1, r1, 0, width), "top": {"style": "SOLID"}}},
                cell(r1, r1 + 1, 0, 1, italic, "userEnteredFormat.textFormat")]
    req += [fmt(EARLY0 - 1, EARLY0 + 2, 13, 14, "0.0%", "PERCENT"), fmt(EARLY0 - 1, EARLY0 + 3, 15, 16, "#,##0"),
            cell(EARLY0 - 1, EARLY0 + 2, 13, 14, yellow, "userEnteredFormat.backgroundColor"),
            cell(PROJ_H - 1, PROJ_H, 0, 7, hdr, hdr_f),
            fmt(PROJ0 - 1, PROJ0 + 3, 1, 6, margin), fmt(PROJ0 - 1, PROJ0 + 3, 6, 7, "0%", "PERCENT"),
            cell(PROJ0 + 2, PROJ0 + 3, 0, 7, {"textFormat": {"bold": True}}, "userEnteredFormat.textFormat"),
            {"updateBorders": {"range": rng(PROJ0 + 2, PROJ0 + 3, 0, 7), "top": {"style": "SOLID"}}},
            cell(PROJ0 - 1, PROJ0 + 3, 5, 6, {"textFormat": {"bold": True}}, "userEnteredFormat.textFormat"),
            cell(DET_H - 1, DET_H, 0, NCOLS, hdr, hdr_f)]
    for name in DET[4:]:
        c = COL[name]
        if name.startswith("%"):
            req.append(fmt(C0 - 1, C1, c, c + 1, "0%", "PERCENT"))
        elif name == "Current margin":
            req.append(fmt(C0 - 1, C1, c, c + 1, margin))
        elif "status" not in name and name not in ("Batch as of", "Share used"):
            req.append(fmt(C0 - 1, C1, c, c + 1, "#,##0"))
    for col in ("Eday status", "Totals status"):
        for status, color in (("done", {"red": 0.72, "green": 0.88, "blue": 0.8}),
                              ("not done", {"red": 1, "green": 0.9, "blue": 0.6})):
            req.append({"addConditionalFormatRule": {"index": 0, "rule": {
                "ranges": [rng(C0 - 1, C1, COL[col], COL[col] + 1)],
                "booleanRule": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": status}]},
                                "format": {"backgroundColor": color}}}}})
    req.append({"addConditionalFormatRule": {"index": 0, "rule": {
        "ranges": [rng(C0 - 1, C1, COL["Path"], COL["Path"] + 1)],
        "booleanRule": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "no votes"}]},
                        "format": {"backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85}}}}}})
    req += group_shading_rules(gid, [(EDAY0 - 1, EDAY0 + 2, 0, 1), (TOT0 - 1, TOT0 + 2, 0, 1),
                                     (EARLY0 - 1, EARLY0 + 2, 0, 1), (PROJ0 - 1, PROJ0 + 2, 0, 1),
                                     (C0 - 1, C1, 2, 3, "A")])
    req += [{"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": a,
                                                     "endIndex": b}, "properties": {"pixelSize": px},
                                           "fields": "pixelSize"}}
            for a, b, px in ((0, 1, 160), (1, NCOLS, 100), (13, 14, 230))]
    r = s.post(api + ":batchUpdate", json={"requests": req})
    if r.status_code != 200:
        raise SystemExit(f"Format request failed: {r.status_code} {r.text[:400]}")
    print(f"projection: Eday / totals-only / Early blocks, cutoff {cutoff}, basis {basis}, "
          f"Early assumptions kept {early_in} -> {sheet_id}")


def main(argv=None) -> int:
    sheet_id = os.environ.get("GSHEET_ID")
    if not sheet_id:
        print("Set GSHEET_ID", file=sys.stderr)
        return 2
    build(sheet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
