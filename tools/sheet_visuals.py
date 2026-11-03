"""Build the 'visuals' tab of the owner's election-night Google Sheet.

Two vote-weighted bubble charts, fed by formula data blocks on the same tab
that read the 'validations' tab, so they update with it (no rebuild needed):

1. Eday turnout vs expected, by county partisanship.
   x = the model's expected Dem 2-way share (validations O, Total expected)
   y = Eday turnout delta = our Eday votes / the model's expected Eday votes - 1
       (validations G - 1); 0 = on expectation
   size = Eday votes counted; colour = group (base blue, rurals red, swing yellow)
   Only counties with Eday votes counted are plotted.

2. Actual vs expected Dem 2-way share, by vote method.
   x = expected 2-way, y = actual 2-way, size = votes counted for that
   method, colour = method (Eday blue, Early red, In-person early yellow, Mail green).

Lines of best fit are vote-weighted least squares, drawn across the plotted
x range: chart 1 has ONE line over all counties (its own colour, green);
chart 2 has one per method, in that method's colour. Google's bubble chart has no trendlines (and the API can't set them on
any chart), so each line is a dense row of tiny points carrying the group's
own label, which gives it the group's colour. The fits are live formulas, in
the fit tables at the right of the tab (n, weighted means, slope, x range).

Stability rows: one tiny ANCHOR point per group comes first, so colours never
depend on which counties have reported (bubble colours follow first
appearance) and the chart always has numbers to draw. Each anchor sits on its
group's fit line once there is one.

Mid-count, chart 1 mostly shows how far each county's Eday count has got;
read it as turnout once a county is fully in.

This script writes only the 'visuals' tab (clears and rewrites it).
Usage:
    GSHEET_ID=<id> python -m tools.sheet_visuals
"""

from __future__ import annotations

import os
import sys

from tools.push_sheet import PROD_IDS, session
from tools.sheet_validations import FIRST, KEY, LAST

TAB = "visuals"
N = LAST - FIRST + 1  # 88 counties
FIT_PTS = 150         # points per best-fit line (dense, so the dots read as a solid line)

GROUP_ORDER = ["base", "rurals", "swing"]
# validations columns for chart 2: method -> (actual share, expected share, votes)
METHODS = [("Eday", "J", "K", "P"), ("Early", "L", "M", "R"),
           ("In-person early", "V", "W", "AB"), ("Mail", "Y", "Z", "AE")]

# column positions (0-based): data blocks and fit tables
B1, B2 = 25, 31           # chart data: Z..AD and AF..AJ (+ empty label column AK)
T1, T2 = 37, 45           # fit tables: AL..AR and AT..AZ
NCOLS = T2 + 7


def L(i: int) -> str:
    s, i = "", i + 1
    while i:
        i, rm = divmod(i - 1, 26)
        s = chr(65 + rm) + s
    return s


def layout(nanchors: int, nfits: int, nrows_data: int) -> dict:
    """Row numbers (1-based) of each part of a data block."""
    anchors = 2
    fits = anchors + nanchors
    data = fits + nfits * FIT_PTS
    return {"anchors": anchors, "fits": fits, "data": data, "end": data + nrows_data - 1}


def fit_table(t: int, b: int, groups: list[str], lay: dict, fallback_y: float,
              by_group: bool = True) -> tuple[list, list]:
    """Fit table at column t for data block at column b. Returns (table rows, per-group cell refs).
    by_group=False: one fit over every plotted point (the label in `groups` is just a name)."""
    g, x, y, w = L(b + 1 if b == B1 else b), L(b + 2), L(b + 3), L(b + 4)
    d0, d1 = lay["data"], lay["end"]
    hdr = ["Fit: group", "n", "mean x", "mean y", "slope", "x min", "x max"]
    rows, refs = [hdr], []
    for i, grp in enumerate(groups):
        r = i + 2
        c = {k: f"{L(t + j)}{r}" for j, k in enumerate(["g", "n", "mx", "my", "b", "x0", "x1"])}

        def F(col):
            cond = f'${g}${d0}:${g}${d1}={c["g"]}, ' if by_group else ""
            return f'FILTER(${col}${d0}:${col}${d1}, {cond}${y}${d0}:${y}${d1}<>"")'
        rows.append([
            grp,
            f'=IFERROR(ROWS({F(x)}),0)',
            f'=IFERROR(SUMPRODUCT({F(w)},{F(x)})/SUM({F(w)}),"")',
            f'=IFERROR(SUMPRODUCT({F(w)},{F(y)})/SUM({F(w)}),"")',
            f'=IFERROR(LET(xs,{F(x)},ys,{F(y)},ws,{F(w)},'
            f'SUMPRODUCT(ws,(xs-{c["mx"]})*(ys-{c["my"]}))/SUMPRODUCT(ws,(xs-{c["mx"]})^2)),"")',
            f'=IFERROR(MIN({F(x)}),"")',
            f'=IFERROR(MAX({F(x)}),"")',
        ])
        refs.append(c)
    return rows, refs


def fit_rows(groups: list[str], refs: list[dict], fallback_y: float, chart: int) -> tuple[list, list]:
    """Anchor rows and best-fit line rows for a data block."""
    def blank_row(grp, x, y):
        return (["", grp, x, y, 0] if chart == 1 else [grp, "", x, y, 0])

    anchors, fits = [], []
    for grp, c in zip(groups, refs):
        ok = f'{c["b"]}<>""'
        anchors.append(blank_row(grp, f'=IF({ok},{c["x0"]},0.5)',
                                 f'=IF({ok},{c["my"]}+{c["b"]}*({c["x0"]}-{c["mx"]}),{fallback_y})'))
        for i in range(FIT_PTS):
            xf = f'{c["x0"]}+({c["x1"]}-{c["x0"]})*{i}/{FIT_PTS - 1}'
            fits.append(blank_row(grp, f'=IF({ok},{xf},"")',
                                  f'=IF({ok},{c["my"]}+{c["b"]}*({xf}-{c["mx"]}),"")'))
    return anchors, fits


FIT1_LABEL = "best fit (all counties)"


def block1(groups_by_county: list[str]) -> tuple[list, list]:
    """Chart 1: one vote-weighted fit over every plotted county. Group anchors sit
    under each group's first plotted county (fallback 50%, 0 if it has none)."""
    lay = layout(len(GROUP_ORDER), 1, N)
    table, refs = fit_table(T1, B1, [FIT1_LABEL], lay, 0, by_group=False)
    _, fits = fit_rows([FIT1_LABEL], refs, 0, 1)
    d0, d1 = lay["data"], lay["end"]
    gc, xc, yc = L(B1 + 1), L(B1 + 2), L(B1 + 3)
    anchors = []
    for grp in GROUP_ORDER:
        def first(col):
            return (f'INDEX(FILTER(${col}${d0}:${col}${d1}, ${gc}${d0}:${gc}${d1}="{grp}", '
                    f'${yc}${d0}:${yc}${d1}<>""),1)')
        anchors.append(["", grp, f"=IFERROR({first(xc)},0.5)", f"=IFERROR({first(yc)},0)", 0])
    rows = [["County", "Group", "Expected Dem 2-way", "Eday turnout delta", "Eday votes"]] + anchors + fits
    order = sorted(range(N), key=lambda k: (GROUP_ORDER.index(groups_by_county[k])
                                            if groups_by_county[k] in GROUP_ORDER else 9, k))
    for k in order:
        v = FIRST + k
        ok = f"AND(validations!G{v}<>\"\",N(validations!P{v})>0)"
        rows.append([f"=validations!C{v}", f"=validations!A{v}", f"=IF({ok},validations!O{v},\"\")",
                     f"=IF({ok},validations!G{v}-1,\"\")", f"=IF({ok},validations!P{v},\"\")"])
    assert len(rows) == lay["end"], (len(rows), lay)
    return rows, table


def block2() -> tuple[list, list]:
    labels = [m[0] for m in METHODS]
    lay = layout(len(labels), len(labels), N * len(METHODS))
    table, refs = fit_table(T2, B2, labels, lay, 0.5)
    anchors, fits = fit_rows(labels, refs, 0.5, 2)
    rows = [["Method", "County", "Expected Dem 2-way", "Actual Dem 2-way", "Votes"]] + anchors + fits
    for lab, a, e, n in METHODS:
        for k in range(N):
            v = FIRST + k
            ok = f"AND(validations!{a}{v}<>\"\",validations!{e}{v}<>\"\",N(validations!{n}{v})>0)"
            rows.append([lab, f"=validations!C{v}", f"=IF({ok},validations!{e}{v},\"\")",
                         f"=IF({ok},validations!{a}{v},\"\")", f"=IF({ok},validations!{n}{v},\"\")"])
    assert len(rows) == lay["end"], (len(rows), lay)
    return rows, table


def build(sheet_id: str) -> None:
    if sheet_id in PROD_IDS:
        raise SystemExit("Refusing to write to the AP aggregator's production sheet.")
    s, _ = session(KEY)
    api = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    sheets = s.get(api, params={"fields": "sheets(properties,charts(chartId))"}).json()["sheets"]
    tab = next((x for x in sheets if x["properties"]["title"] == TAB), None)
    if tab is None:
        gid = s.post(api + ":batchUpdate", json={"requests": [{"addSheet": {"properties": {"title": TAB}}}]}
                     ).json()["replies"][0]["addSheet"]["properties"]["sheetId"]
        charts = []
    else:
        gid, charts = tab["properties"]["sheetId"], [c["chartId"] for c in tab.get("charts", [])]

    groups = [r[0] if r else "" for r in s.get(f"{api}/values/validations!A{FIRST}:A{LAST}").json()["values"]]
    groups += [""] * (N - len(groups))
    b1, t1 = block1(groups)
    b2, t2 = block2()
    nrows = max(len(b1), len(b2)) + 2

    req = [{"deleteEmbeddedObject": {"objectId": c}} for c in charts]
    req += [{"updateCells": {"range": {"sheetId": gid}, "fields": "userEnteredValue,userEnteredFormat"}},
            {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {
                "rowCount": nrows, "columnCount": NCOLS}},
                "fields": "gridProperties(rowCount,columnCount)"}}]
    s.post(api + ":batchUpdate", json={"requests": req}).raise_for_status()
    # chart 2's label column: a single space per row. The chart refuses to draw
    # ("Column 1 must be numeric") if its label column holds no text at all.
    labels2 = [["Label"]] + [[" "] for _ in range(len(b2) - 1)]
    for col, data in ((B1, b1), (B2, b2), (B2 + 5, labels2), (T1, t1), (T2, t2)):
        s.put(f"{api}/values/{TAB}!{L(col)}1", params={"valueInputOption": "USER_ENTERED"},
              json={"values": data}).raise_for_status()
    s.put(f"{api}/values/{TAB}!{L(B1)}{nrows}", params={"valueInputOption": "RAW"},
          json={"values": [["Chart data and fits: formulas reading the validations tab. "
                            "Rebuilt by tools/sheet_visuals.py."]]}).raise_for_status()

    def rng(c0, c1, r0=0, r1=None):
        return {"sheetId": gid, "startRowIndex": r0, "endRowIndex": r1 or nrows,
                "startColumnIndex": c0, "endColumnIndex": c1}

    def src(c, n):  # data rows only: a header row would show up as an extra legend entry
        return {"sourceRange": {"sources": [rng(c, c + 1, 1, n)]}}

    def fmt(c0, c1, pattern, typ, r1=None):
        return {"repeatCell": {"range": rng(c0, c1, 1, r1),
                               "cell": {"userEnteredFormat": {"numberFormat": {"type": typ, "pattern": pattern}}},
                               "fields": "userEnteredFormat.numberFormat"}}

    req = [fmt(B1 + 2, B1 + 3, "0%", "PERCENT"), fmt(B1 + 3, B1 + 4, "+0%;-0%;0%", "PERCENT"),
           fmt(B1 + 4, B1 + 5, "#,##0", "NUMBER"), fmt(B2 + 2, B2 + 4, "0%", "PERCENT"),
           fmt(B2 + 4, B2 + 5, "#,##0", "NUMBER"),
           fmt(T1 + 2, T1 + 3, "0.0%", "PERCENT", 4), fmt(T1 + 3, T1 + 4, "+0.0%;-0.0%", "PERCENT", 4),
           fmt(T1 + 4, T1 + 5, "0.00", "NUMBER", 4), fmt(T1 + 5, T1 + 7, "0.0%", "PERCENT", 4),
           fmt(T2 + 2, T2 + 4, "0.0%", "PERCENT", 5), fmt(T2 + 4, T2 + 5, "0.00", "NUMBER", 5),
           fmt(T2 + 5, T2 + 7, "0.0%", "PERCENT", 5),
           {"repeatCell": {"range": rng(B1, NCOLS, 0, 1),
                           "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                           "fields": "userEnteredFormat.textFormat.bold"}}]
    n1, n2 = len(b1), len(b2)

    def bubble(title, subtitle, c, gcol, labels, n, row):
        spec = {"domain": src(c + 2, n), "series": src(c + 3, n), "groupIds": src(gcol, n),
                "bubbleSizes": src(c + 4, n), "bubbleLabels": src(labels, n), "bubbleOpacity": 0.6,
                "bubbleMinRadiusSize": 4, "bubbleMaxRadiusSize": 40, "legendPosition": "RIGHT_LEGEND",
                # no outline: at line-dot size a black outline is all you would see
                "bubbleBorderColorStyle": {"rgbColor": {"red": 1, "green": 1, "blue": 1, "alpha": 0}},
                "bubbleTextStyle": {"fontSize": 8}}
        return {"addChart": {"chart": {
            "spec": {"title": title, "subtitle": subtitle, "bubbleChart": spec},
            "position": {"overlayPosition": {"anchorCell": {"sheetId": gid, "rowIndex": row, "columnIndex": 0},
                                             "widthPixels": 1100, "heightPixels": 560}}}}}

    req.append(bubble("Eday turnout vs expected, by county partisanship",
                      "x: model's expected Dem 2-way share | y: Eday votes vs model's expected Eday votes "
                      "(0 = on expectation) | size: Eday votes counted | line: vote-weighted best fit, all counties",
                      B1, B1 + 1, B1, n1, 0))
    req.append(bubble("Actual vs expected Dem 2-way share, by vote method",
                      "x: model's expected Dem 2-way | y: actual Dem 2-way | size: votes counted for that method "
                      "| lines: vote-weighted best fit per method",
                      B2, B2, B2 + 5, n2, 30))
    r = s.post(api + ":batchUpdate", json={"requests": req})
    if r.status_code != 200:
        raise SystemExit(f"Chart request failed: {r.status_code} {r.text[:500]}")
    print(f"visuals: 2 bubble charts with best-fit lines -> {sheet_id}")


def main(argv=None) -> int:
    sheet_id = os.environ.get("GSHEET_ID")
    if not sheet_id:
        print("Set GSHEET_ID", file=sys.stderr)
        return 2
    build(sheet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
