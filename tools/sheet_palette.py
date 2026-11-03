"""One colour scheme for the owner's election-night sheet.

Groups (base / swing / rurals) use the same colour everywhere: the bubbles in
'visuals' and the shaded group cells in 'Topline', 'validations' and
'grouping'. Eday / Early (chart 2) use different colours entirely.

Bubble charts can't be given per-group colours through the API; they take the
spreadsheet theme's ACCENT1..6 in the order groups first appear. So the theme
accents ARE the palette:
    ACCENT1 base, ACCENT2 rurals, ACCENT3 swing, ACCENT4 chart-1 fit line,
    ACCENT5 Eday, ACCENT6 Early
Chart 1 lists base, rurals, swing, fit (accents 1-4). Chart 2 starts with four
padding groups so Eday and Early land on accents 5 and 6.

Cell shading uses each colour as it renders in the charts (bubbles are drawn at
60% opacity on white), so a shaded 'base' cell looks like a base bubble.

Usage (applies the theme + the Topline / grouping shading; the validations
shading is applied by tools/sheet_validations.py since it rebuilds that tab):
    GSHEET_ID=<id> python -m tools.sheet_palette
"""

from __future__ import annotations

import os
import re
import sys

from tools.push_sheet import PROD_IDS, session

OPACITY = 0.6
# name -> rgb (0-1)
COLORS = {
    "base": (0.235, 0.471, 0.847),     # blue
    "rurals": (0.800, 0.000, 0.000),   # red
    "swing": (0.557, 0.267, 0.678),    # purple
    "fit": (0.263, 0.263, 0.263),      # dark grey (chart 1 best-fit line)
    "Eday": (0.000, 0.537, 0.482),     # teal
    "Early": (0.961, 0.486, 0.000),    # orange
}
ACCENT_ORDER = ["base", "rurals", "swing", "fit", "Eday", "Early"]
GROUPS = ["base", "swing", "rurals"]
CHART2_PADDING = 4  # padding groups before Eday/Early in chart 2


def rgb(name: str) -> dict:
    r, g, b = COLORS[name]
    return {"red": r, "green": g, "blue": b}


def tint(name: str) -> dict:
    """The colour as a bubble renders it: OPACITY over white."""
    return {k: round(v * OPACITY + (1 - OPACITY), 4) for k, v in rgb(name).items()}


def group_shading_rules(sheet_id: int, ranges: list[tuple]) -> list[dict]:
    """addConditionalFormatRule requests for group colours.
    Each range is (start_row, end_row, start_col, end_col[, key_col]), 0-based, end exclusive.
    Without key_col: shade cells whose own text is a group name (e.g. the 'base' label rows).
    With key_col (a column letter): shade by the group in that column on the same row, e.g. the
    county-name cell when the group column itself is hidden."""
    out = []
    for a, b, c, d, *key in ranges:
        rng = {"sheetId": sheet_id, "startRowIndex": a, "endRowIndex": b,
               "startColumnIndex": c, "endColumnIndex": d}
        for g in GROUPS:
            if key:
                cond = {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f'=${key[0]}{a + 1}="{g}"'}]}
            else:
                cond = {"type": "TEXT_EQ", "values": [{"userEnteredValue": g}]}
            out.append({"addConditionalFormatRule": {"index": 0, "rule": {
                "ranges": [rng], "booleanRule": {"condition": cond, "format": {"backgroundColor": tint(g)}}}}})
    return out


def is_group_rule(rule: dict) -> bool:
    """True for rules made by group_shading_rules (so a rerun can replace them)."""
    c = rule.get("booleanRule", {}).get("condition", {})
    vals = [v.get("userEnteredValue") for v in c.get("values", [])]
    if c.get("type") == "TEXT_EQ":
        return vals in ([[g] for g in GROUPS])
    if c.get("type") == "CUSTOM_FORMULA" and len(vals) == 1:
        return bool(re.fullmatch(r'=\$[A-Z]+\d+="(' + "|".join(GROUPS) + r')"', vals[0] or ""))
    return False


def apply(sheet_id: str) -> None:
    from tools.sheet_validations import KEY
    if sheet_id in PROD_IDS:
        raise SystemExit("Refusing to write to the AP aggregator's production sheet.")
    s, _ = session(KEY)
    api = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
    meta = s.get(api, params={"fields": "properties.spreadsheetTheme,sheets(properties(title,sheetId),"
                                        "conditionalFormats)"}).json()
    theme = meta["properties"]["spreadsheetTheme"]
    for tc in theme["themeColors"]:
        if tc["colorType"].startswith("ACCENT"):
            tc["color"] = {"rgbColor": rgb(ACCENT_ORDER[int(tc["colorType"][-1]) - 1])}
    req = [{"updateSpreadsheetProperties": {"properties": {"spreadsheetTheme": theme},
                                            "fields": "spreadsheetTheme"}}]
    sheets = {x["properties"]["title"]: x for x in meta["sheets"]}
    targets = {
        # C4:C6 group rows; county names C13:C100 by the (hidden) group column A
        "Topline": [(3, 6, 2, 3), (12, 100, 2, 3, "A")],
        "grouping": [(0, 1000, 2, 3)],                # column C
    }
    for title, ranges in targets.items():
        sh = sheets[title]
        gid = sh["properties"]["sheetId"]
        # drop rules this script added before (deleting from the end keeps indices valid)
        for i in reversed([i for i, cf in enumerate(sh.get("conditionalFormats", [])) if is_group_rule(cf)]):
            req.append({"deleteConditionalFormatRule": {"sheetId": gid, "index": i}})
        req += group_shading_rules(gid, ranges)
    r = s.post(api + ":batchUpdate", json={"requests": req})
    if r.status_code != 200:
        raise SystemExit(f"Palette update failed: {r.status_code} {r.text[:400]}")
    print(f"palette: theme accents set; group shading on Topline and grouping -> {sheet_id}")


def main(argv=None) -> int:
    sheet_id = os.environ.get("GSHEET_ID")
    if not sheet_id:
        print("Set GSHEET_ID", file=sys.stderr)
        return 2
    apply(sheet_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
