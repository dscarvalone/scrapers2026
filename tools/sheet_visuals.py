"""Build the 'visuals' tab of the owner's election-night Google Sheet.

Two vote-weighted bubble charts, fed by formula data blocks on the same tab
that read the 'validations' tab (so they update with it):

1. Eday turnout vs expected, by county partisanship.
   x = the model's expected Dem 2-way share (validations O, Total expected)
   y = Eday turnout delta = our Eday votes / the model's expected Eday votes - 1
       (validations G - 1); 0 = on expectation
   size = Eday votes counted; colour = group (base / swing / rurals)
   Only counties with Eday votes counted are plotted.

2. Actual vs expected Dem 2-way share, by vote method.
   x = expected 2-way, y = actual 2-way, size = votes counted for that
   method, colour = method (Eday blue, Early red, In-person early yellow,
   Mail green; colours follow the order groups first appear). A row of tiny
   orange points along y = x is the reference line: above it, Brown is
   beating the model for that county and method.

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

# data block 1 at columns Z..AD (25..29), block 2 at AF..AJ (31..35)
B1, B2 = 25, 31
# validations columns for chart 2: method -> (actual share, expected share, votes)
METHODS = [("Eday", "J", "K", "P"), ("Early", "L", "M", "R"),
           ("In-person early", "V", "W", "AB"), ("Mail", "Y", "Z", "AE")]
REF = [round(0.1 + 0.025 * i, 3) for i in range(33)]  # y = x reference points, 10%..90%


def L(i: int) -> str:
    s, i = "", i + 1
    while i:
        i, rm = divmod(i - 1, 26)
        s = chr(65 + rm) + s
    return s


GROUP_ORDER = ["base", "rurals", "swing"]  # bubble colours follow first appearance: blue, red, yellow


# Fixed rows that keep the charts stable whatever has reported:
#  - one tiny ANCHOR point per colour group, first, so colours never depend on
#    which counties have votes yet (bubble colours follow first appearance) and
#    every numeric column always has a number (an all-blank column errors);
#  - a reference line of tiny dots, last;
#  - one SCALE dot whose size is 30 until any votes are counted, then 1, so the
#    reference dots stay small before results (bubble sizes are relative).
REF1 = [round(0.2 + 0.025 * i, 3) for i in range(27)]  # y = 0 line, x 20%..85%


def block1(groups: list[str]) -> list[list]:
    rows = [["County", "Group", "Expected Dem 2-way", "Eday turnout delta", "Eday votes"]]
    rows += [["", g, 0.5, 0, 1] for g in GROUP_ORDER]
    first = len(rows) + 1
    order = sorted(range(N), key=lambda k: (GROUP_ORDER.index(groups[k]) if groups[k] in GROUP_ORDER else 9, k))
    for k in order:
        v = FIRST + k
        ok = f"AND(validations!G{v}<>\"\",N(validations!P{v})>0)"
        rows.append([f"=validations!C{v}", f"=validations!A{v}", f"=IF({ok},validations!O{v},\"\")",
                     f"=IF({ok},validations!G{v}-1,\"\")", f"=IF({ok},validations!P{v},\"\")"])
    last = len(rows)
    rows += [["", "expected (0)", x, 0, 1] for x in REF1]
    vcol = L(B1 + 4)
    rows.append(["", "expected (0)", REF1[0], 0, f"=IF(MAX({vcol}{first}:{vcol}{last})=0,30,1)"])
    return rows


def block2() -> list[list]:
    rows = [["Method", "County", "Expected Dem 2-way", "Actual Dem 2-way", "Votes"]]
    rows += [[lab, "", 0.5, 0.5, 1] for lab, _, _, _ in METHODS]
    first = len(rows) + 1
    for lab, a, e, n in METHODS:
        for k in range(N):
            v = FIRST + k
            ok = f"AND(validations!{a}{v}<>\"\",validations!{e}{v}<>\"\",N(validations!{n}{v})>0)"
            rows.append([lab, f"=validations!C{v}", f"=IF({ok},validations!{e}{v},\"\")",
                         f"=IF({ok},validations!{a}{v},\"\")", f"=IF({ok},validations!{n}{v},\"\")"])
    last = len(rows)
    for x in REF:
        rows.append(["y = x", "", x, x, 1])
    vcol = L(B2 + 4)
    rows.append(["y = x", "", REF[0], REF[0], f"=IF(MAX({vcol}{first}:{vcol}{last})=0,30,1)"])
    return rows


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
    b1, b2 = block1(groups), block2()
    nrows = max(len(b1), len(b2))
    req = [{"deleteEmbeddedObject": {"objectId": c}} for c in charts]
    req += [{"updateCells": {"range": {"sheetId": gid}, "fields": "userEnteredValue,userEnteredFormat"}},
            {"updateSheetProperties": {"properties": {"sheetId": gid, "gridProperties": {
                "rowCount": nrows + 2, "columnCount": B2 + 6}},
                "fields": "gridProperties(rowCount,columnCount)"}}]
    s.post(api + ":batchUpdate", json={"requests": req}).raise_for_status()
    for col, data in ((B1, b1), (B2, b2)):
        s.put(f"{api}/values/{TAB}!{L(col)}1", params={"valueInputOption": "USER_ENTERED"},
              json={"values": data}).raise_for_status()
    s.put(f"{api}/values/{TAB}!{L(B1)}{nrows + 2}", params={"valueInputOption": "RAW"},
          json={"values": [["Chart data: formulas reading the validations tab. Rebuilt by tools/sheet_visuals.py."]]}
          ).raise_for_status()

    def rng(c0, c1, r0=0, r1=None):
        return {"sheetId": gid, "startRowIndex": r0, "endRowIndex": r1 or nrows,
                "startColumnIndex": c0, "endColumnIndex": c1}

    def src(c, n):  # data rows only: a header row would show up as an extra legend entry
        return {"sourceRange": {"sources": [rng(c, c + 1, 1, n)]}}

    def fmt(c0, c1, pattern, typ):
        return {"repeatCell": {"range": rng(c0, c1, 1, nrows),
                               "cell": {"userEnteredFormat": {"numberFormat": {"type": typ, "pattern": pattern}}},
                               "fields": "userEnteredFormat.numberFormat"}}

    req = [fmt(B1 + 2, B1 + 3, "0%", "PERCENT"), fmt(B1 + 3, B1 + 4, "+0%;-0%;0%", "PERCENT"),
           fmt(B1 + 4, B1 + 5, "#,##0", "NUMBER"), fmt(B2 + 2, B2 + 4, "0%", "PERCENT"),
           fmt(B2 + 4, B2 + 5, "#,##0", "NUMBER"),
           {"repeatCell": {"range": rng(B1, B2 + 5, 0, 1),
                           "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                           "fields": "userEnteredFormat.textFormat.bold"}}]
    n1, n2 = len(b1), len(b2)

    def bubble(title, subtitle, c, n, labels, row):
        spec = {"domain": src(c + 2, n), "series": src(c + 3, n), "groupIds": src(c if c == B2 else c + 1, n),
                "bubbleSizes": src(c + 4, n), "bubbleOpacity": 0.6, "bubbleMinRadiusSize": 3,
                "bubbleMaxRadiusSize": 40, "legendPosition": "RIGHT_LEGEND",
                "bubbleTextStyle": {"fontSize": 8}}
        # the API requires a label column; chart 2 points at an empty one (column after its data)
        spec["bubbleLabels"] = src(c if labels else c + 5, n)
        return {"addChart": {"chart": {
            "spec": {"title": title, "subtitle": subtitle, "bubbleChart": spec},
            "position": {"overlayPosition": {"anchorCell": {"sheetId": gid, "rowIndex": row, "columnIndex": 0},
                                             "widthPixels": 1100, "heightPixels": 560}}}}}

    req.append(bubble("Eday turnout vs expected, by county partisanship",
                      "x: model's expected Dem 2-way share | y: Eday votes vs model's expected Eday votes "
                      "| size: Eday votes counted | colour: group | small green dots = on expectation (0)",
                      B1, n1, True, 0))
    req.append(bubble("Actual vs expected Dem 2-way share, by vote method",
                      "x: model's expected Dem 2-way | y: actual Dem 2-way | size: votes counted for that method "
                      "| small orange dots = the y = x line (above it = Brown beating the model)",
                      B2, n2, False, 30))
    r = s.post(api + ":batchUpdate", json={"requests": req})
    if r.status_code != 200:
        raise SystemExit(f"Chart request failed: {r.status_code} {r.text[:500]}")
    print(f"visuals: 2 bubble charts, {n1 - 1} county rows + {n2 - 1} method rows -> {sheet_id}")


def main(argv=None) -> int:
    sheet_id = os.environ.get("GSHEET_ID")
    if not sheet_id:
        print("Set GSHEET_ID", file=sys.stderr)
        return 2
    build(sheet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
