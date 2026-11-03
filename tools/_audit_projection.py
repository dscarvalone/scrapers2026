"""Audit the projection tab: recompute every county and summary cell in Python from
the validations tab and the tab's own inputs, and compare.

Usage: GSHEET_ID=<id> python -m tools._audit_projection
"""
import os

from tools.push_sheet import session
from tools.sheet_projection import C0, C1, GROUPS, SCEN0, SUM0
from tools.sheet_validations import FIRST, KEY, LAST

sid = os.environ["GSHEET_ID"]
s, _ = session(KEY)
base = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/"


def get(rng):
    return s.get(base + rng, params={"valueRenderOption": "UNFORMATTED_VALUE"}).json().get("values", [])


def col(c):
    n = 0
    for ch in c:
        n = n * 26 + ord(ch) - 64
    return n - 1


P = [r + [""] * (14 - len(r)) for r in get(f"projection!A1:N{C1}")]
Vd = [r + [""] * (60 - len(r)) for r in get(f"validations!A{FIRST}:BH{LAST}")]
num = lambda x: 0 if x == "" else x
cut = P[1][1]
n = bad = 0


def check(where, e, g):
    global n, bad
    n += 1
    ok = e == g or (isinstance(e, (int, float)) and isinstance(g, (int, float)) and abs(e - g) <= 1e-6 * max(1, abs(e)))
    if not ok:
        bad += 1
        if bad <= 8:
            print("MISMATCH", where, repr(e), repr(g))


recs = []
for k, v in enumerate(Vd):
    row = P[C0 - 1 + k]
    g = lambda c: v[col(c)]
    D, E = g("P"), g("Q")
    F = "" if D == "" or E == "" or num(E) == 0 else D / E
    G = "no Eday count" if F == "" else ("done" if F >= cut else "not done")
    H = num(g("AQ")) - num(g("AR"))
    I = g("J") if g("J") != "" else g("K")
    K = "" if G == "no Eday count" else (0 if G == "done" else max(0, E - D))
    Lm = "" if K == "" or I == "" else (2 * I - 1) * K
    M = H + num(Lm)
    exp = [g("A"), g("C"), D, E, F, G, H, I, K, Lm, M, num(g("U"))]
    got = [row[0], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[10], row[11], row[12], row[13]]
    for j, (e, x) in enumerate(zip(exp, got)):
        check((g("C"), j), e, x)
    recs.append(dict(grp=g("A"), st=G, H=H, K=num(K), L=num(Lm), M=M, N=num(g("U"))))

mail = {}
for i, grp in enumerate(GROUPS):
    r = P[SCEN0 - 1 + i]
    check((grp, "mail margin"), (2 * num(r[3]) - 1) * num(r[2]), r[4])
    mail[grp] = (2 * num(r[3]) - 1) * num(r[2])

for i, grp in enumerate(["FINAL"] + GROUPS):
    r = P[SUM0 - 1 + i]
    sub = [x for x in recs if grp == "FINAL" or x["grp"] == grp]
    tot_n = sum(x["N"] for x in sub)
    nc = sum(x["N"] for x in sub if x["st"] == "no Eday count")
    em = sum(x["M"] for x in sub)
    mm = sum(mail.values()) if grp == "FINAL" else mail[grp]
    exp = [grp, sum(x["st"] == "done" for x in sub), sum(x["st"] == "not done" for x in sub),
           sum(x["st"] == "no Eday count" for x in sub), nc / tot_n if tot_n else "",
           sum(x["H"] for x in sub), sum(x["K"] for x in sub), sum(x["L"] for x in sub), em, mm, em + mm]
    for j, e in enumerate(exp):
        check((grp, "summary", j), e, r[j])

print("error cells", [(i + 1, j) for i, r in enumerate(P) for j, x in enumerate(r) if str(x).startswith("#")][:5])
print("cells compared", n, "mismatches", bad)
