"""Audit the validations tab: recompute every county and group cell in Python
straight from the methods / 'dscc data tab' / grouping tabs and compare.

Usage: GSHEET_ID=<id> python -m tools._audit_validations
"""
import os

from tools.push_sheet import session
from tools.sheet_validations import FIRST, GROUPS, KEY, METHODS, NCOLS, SOURCE_COL

SID = os.environ["GSHEET_ID"]
s, _ = session(KEY)
base = f"https://sheets.googleapis.com/v4/spreadsheets/{SID}/values/"


def get(rng, render="UNFORMATTED_VALUE"):
    return s.get(base + rng, params={"valueRenderOption": render}).json().get("values", [])


V = [r + [""] * (NCOLS - len(r)) for r in get("validations!A1:BB97")]
mh = get("methods!1:1")[0]
MR = {r[2]: dict(zip(mh, r)) for r in get("methods!A2:ZZ90") if len(r) > 2}
ah = get("'dscc data tab'!D6:ZZ6")[0]
AR = {r[0]: dict(zip(ah, r)) for r in get("'dscc data tab'!D7:ZZ200") if r}
grp = {str(r[0]): r[2] for r in get("grouping!A1:C200") if len(r) > 2}

errors = [(i + 1, j) for i, r in enumerate(V) for j, x in enumerate(r) if str(x).startswith("#")]
n = bad = 0


def same(e, g):
    return e == g or (isinstance(e, (int, float)) and isinstance(g, (int, float))
                      and abs(e - g) <= 1e-9 * max(1, abs(e)))


def check(where, e, g):
    global n, bad
    n += 1
    if not same(e, g):
        bad += 1
        if bad <= 8:
            print("MISMATCH", where, repr(e), repr(g))


county = {}
for row in V[FIRST - 1:]:
    c = row[2]
    m, a = MR[c], AR[c]
    rec = {"group": grp[str(row[1])]}
    check((c, "group"), rec["group"], row[0])
    for k, (_, src, ap, ep, (sa, se, sd), (va, ve, vp), hs) in METHODS.items():
        act = m if src == "M" else a
        sh_a, sh_e = act.get(ap + "two_way", ""), a.get(ep + "two_way", "")
        d = "" if sh_a == "" or sh_e == "" else sh_a - sh_e
        v_a, v_e = act.get(ap + "total_votes", ""), a.get(ep + "total_votes", "")
        p = "" if v_a == "" or v_e in ("", 0) else v_a / v_e
        for col, e in ((sa, sh_a), (se, sh_e), (sd, d), (va, v_a), (ve, v_e), (vp, p)):
            check((c, k, col), e, row[col])
        num = lambda x: 0 if x == "" else x
        rec[k] = dict(d=d, p=p, va=num(v_a), ve=num(v_e),
                      ad=num(act.get(ap + "dem_votes", "")), ag=num(act.get(ap + "gop_votes", "")),
                      ed=num(a.get(ep + "dem_votes", "")), eg=num(a.get(ep + "gop_votes", "")))
    check((c, "source"), m.get("method_source", ""), row[SOURCE_COL])
    county[c] = rec

for i, g in enumerate(GROUPS):
    row = V[2 + i]
    check((g, "label"), g, row[2])
    members = [r for r in county.values() if g == "FINAL" or r["group"] == g]
    for k, (_, _, _, _, (sa, se, sd), (va, ve, vp), _) in METHODS.items():
        sub = [r[k] for r in members if r[k]["d"] != ""]
        ad, ag = sum(x["ad"] for x in sub), sum(x["ag"] for x in sub)
        ed, eg = sum(x["ed"] for x in sub), sum(x["eg"] for x in sub)
        sa_ = ad / (ad + ag) if sub and ad + ag else ""
        se_ = ed / (ed + eg) if sub and ed + eg else ""
        sd_ = sa_ - se_ if sa_ != "" and se_ != "" else ""
        vs = [r[k] for r in members if r[k]["p"] != ""]
        va_ = sum(x["va"] for x in vs) if vs else ""
        ve_ = sum(x["ve"] for x in vs) if vs else ""
        vp_ = va_ / ve_ if vs and ve_ else ""
        for col, e in ((sa, sa_), (se, se_), (sd, sd_), (va, va_), (ve, ve_), (vp, vp_)):
            check((g, k, col), e, row[col])
    nit = sum(1 for c, r in county.items() if (g == "FINAL" or r["group"] == g)
              and MR[c].get("method_source") == "itemized")
    check((g, "source"), f"{nit} itemized", row[SOURCE_COL])

print("error cells", errors[:5])
print("cells compared", n, "mismatches", bad)
for row in V[2:6]:
    print(row[2], [round(x, 3) if isinstance(x, float) else x for x in row[3:9]], row[SOURCE_COL])
