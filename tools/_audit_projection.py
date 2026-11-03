"""Audit the projection tab: recompute every county detail cell, the Eday /
Totals-only / Early blocks and the projected margin in Python straight from the
'methods' and 'validations' tabs and the tab's own inputs, and compare.

Usage: GSHEET_ID=<id> python -m tools._audit_projection
"""
import os

from tools.push_sheet import session
from tools.sheet_projection import (C0, C1, COL, DET, EARLY0, EDAY0, GROUPS, NCOLS, PROJ0, TOT0)
from tools.sheet_validations import FIRST, KEY, LAST

sid = os.environ["GSHEET_ID"]
s, _ = session(KEY)
base = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/"


def get(rng):
    return s.get(base + rng, params={"valueRenderOption": "UNFORMATTED_VALUE"}).json().get("values", [])


def ci(c):
    n = 0
    for ch in c:
        n = n * 26 + ord(ch) - 64
    return n - 1


P = [r + [""] * (NCOLS - len(r)) for r in get(f"projection!A1:AH{C1}")]
Vd = [r + [""] * (60 - len(r)) for r in get(f"validations!A{FIRST}:BH{LAST}")]
mh = get("methods!1:1")[0]
MR = {r[2]: dict(zip(mh, r)) for r in get("methods!A2:ZZ90") if len(r) > 2}
num = lambda x: 0 if x in ("", None) else x
cut, basis = P[1][1], P[2][1]
n = bad = 0


def check(where, e, g):
    global n, bad
    n += 1
    ok = e == g or (isinstance(e, (int, float)) and isinstance(g, (int, float))
                    and abs(e - g) <= 1e-6 * max(1, abs(e)))
    if not ok:
        bad += 1
        if bad <= 10:
            print("MISMATCH", where, repr(e), repr(g))


recs = []
for k, v in enumerate(Vd):
    g = lambda c: v[ci(c)]
    county = g("C")
    m = MR.get(county, {})
    e = {}
    tot_in = num(m.get("total_votes"))
    e["Path"] = "no votes" if tot_in == 0 else ("Eday count" if g("P") != "" else "totals only")
    eday, tot = e["Path"] == "Eday count", e["Path"] == "totals only"
    bd, br, bt = m.get("batch_dem_votes", ""), m.get("batch_gop_votes", ""), m.get("batch_total_votes", "")
    e.update({"Batch Dem": bd, "Batch Rep": br, "Batch total": bt, "Batch as of": m.get("batch_as_of", "")})
    for name, val in (("Eday votes in", num(g("P"))), ("Dem Eday", num(g("AI"))), ("Rep Eday", num(g("AJ"))),
                      ("Expected Eday", num(g("Q")))):
        e[name] = val if eday else ""
    e["% of exp. Eday"] = e["Eday votes in"] / e["Expected Eday"] if eday and num(e["Expected Eday"]) > 0 else ""
    e["Eday status"] = "" if e["% of exp. Eday"] == "" else ("done" if e["% of exp. Eday"] >= cut else "not done")
    e["Eday outstanding"] = ("" if not eday else 0 if e["Eday status"] == "done"
                             else max(0, e["Expected Eday"] - e["Eday votes in"]))
    use_batch = basis == "latest batch" and num(bt) > 0
    if use_batch:
        ds, rs = bd / bt, br / bt
    elif eday and num(e["Eday votes in"]) > 0:
        ds, rs = e["Dem Eday"] / e["Eday votes in"], e["Rep Eday"] / e["Eday votes in"]
    else:
        ds = rs = ""
    for name, sh in (("Eday out Dem", ds), ("Eday out Rep", rs)):
        e[name] = "" if e["Eday outstanding"] == "" or sh == "" else e["Eday outstanding"] * sh
    e["Total votes in"], e["Dem total"], e["Rep total"] = tot_in, num(m.get("dem_votes")), num(m.get("gop_votes"))
    e["Expected total"] = num(g("U")) if tot else ""
    e["% of exp. total"] = tot_in / e["Expected total"] if tot and num(e["Expected total"]) > 0 else ""
    e["Totals status"] = "" if e["% of exp. total"] == "" else ("done" if e["% of exp. total"] >= cut else "not done")
    e["Totals outstanding"] = ("" if not tot else 0 if e["Totals status"] == "done"
                               else max(0, e["Expected total"] - tot_in))
    if num(bt) > 0:
        tds, trs = bd / bt, br / bt
    elif tot_in > 0:
        tds, trs = e["Dem total"] / tot_in, e["Rep total"] / tot_in
    else:
        tds = trs = ""
    for name, sh in (("Totals out Dem", tds), ("Totals out Rep", trs)):
        e[name] = "" if e["Totals outstanding"] == "" or sh == "" else e["Totals outstanding"] * sh
    has_early = g("R") != ""
    e["Early votes in"] = g("R") if has_early else ""
    e["Dem Early"] = num(g("AM")) if has_early else ""
    e["Rep Early"] = num(g("AN")) if has_early else ""
    e["Expected Early"] = num(g("S")) if has_early else ""
    e["Early outstanding"] = max(0, e["Expected Early"] - e["Early votes in"]) if has_early else ""
    if eday:
        e["Share used"] = ("Eday: latest batch" if use_batch else
                           "Eday so far" if num(e["Eday votes in"]) > 0 else "no Eday votes yet")
    elif tot:
        e["Share used"] = "latest batch" if num(bt) > 0 else "current total"
    else:
        e["Share used"] = "not projected"
    e["Current margin"] = e["Dem total"] - e["Rep total"]
    e["Expected total (coverage)"] = num(g("U"))
    e["Group"], e["County"] = g("A"), county
    row = P[C0 - 1 + k]
    for name in DET:
        if name == "FIPS":
            continue
        check((county, name), e[name], row[COL[name]])
    recs.append(e)


def block(sub, kind, assumption=""):
    if kind == "eday":
        sub = [x for x in sub if x["Path"] == "Eday count"]
        keys = ("Eday votes in", "Dem Eday", "Rep Eday", "Expected Eday", "Eday outstanding", "Eday out Dem",
                "Eday out Rep")
    elif kind == "totals":
        sub = [x for x in sub if x["Path"] == "totals only"]
        keys = ("Total votes in", "Dem total", "Rep total", "Expected total", "Totals outstanding", "Totals out Dem",
                "Totals out Rep")
    else:
        keys = ("Early votes in", "Dem Early", "Rep Early", "Expected Early", "Early outstanding")
    sums = [sum(num(x[k]) for x in sub) for k in keys]
    B, C, D, E, J = sums[:5]
    F = B / E if E else ""
    G = C / B if B > 0 else ""
    H = D / B if B > 0 else ""
    I = "" if G == "" else G - H
    if kind == "early":
        if assumption != "":
            tw = 1 if G == "" else G + H
            K, Lr = J * tw * assumption, J * tw * (1 - assumption)
        else:
            K = "" if G == "" else J * G
            Lr = "" if H == "" else J * H
        Mc = "" if K == "" else K - Lr
    else:
        K, Lr = sums[5], sums[6]
        Mc = K - Lr
    return [B, C, D, E, F, G, H, I, J, K, Lr, Mc]


ch = {"eday": {}, "totals": {}, "early": {}}
for i, grp in enumerate(GROUPS):
    sub = [x for x in recs if x["Group"] == grp]
    for kind, first in (("eday", EDAY0), ("totals", TOT0), ("early", EARLY0)):
        row = P[first - 1 + i]
        exp = block(sub, kind, row[13] if kind == "early" else "")
        for j, e in enumerate(exp):
            check((grp, kind, j), e, row[1 + j])
        ch[kind][grp] = num(exp[11])
    pr = P[PROJ0 - 1 + i]
    cur = sum(x["Current margin"] for x in sub)
    tot_proj = cur + ch["eday"][grp] + ch["totals"][grp] + ch["early"][grp]
    for j, e in enumerate([cur, ch["eday"][grp], ch["totals"][grp], ch["early"][grp], tot_proj]):
        check((grp, "proj", j), e, pr[1 + j])
    cov = sum(x["Expected total (coverage)"] for x in sub)
    check((grp, "not projected"), sum(x["Expected total (coverage)"] for x in sub if x["Path"] == "no votes") / cov,
          pr[6])
tr = P[PROJ0 + 2]
cur = sum(x["Current margin"] for x in recs)
parts = [sum(ch[k].values()) for k in ("eday", "totals", "early")]
for j, e in enumerate([cur] + parts + [cur + sum(parts)]):
    check(("Total", "proj", j), e, tr[1 + j])

print("error cells", [(i + 1, j) for i, r in enumerate(P) for j, x in enumerate(r) if str(x).startswith("#")][:5])
print(f"cells compared {n} mismatches {bad}  (cutoff {cut}, basis {basis})")
