"""Audit the projection tab: recompute the county detail, the Mail and Eday
blocks and the projected-margin rollup in Python from the validations tab and
the tab's own inputs, and compare with what the sheet shows.

Usage: GSHEET_ID=<id> python -m tools._audit_projection
"""
import os

from tools.push_sheet import session
from tools.sheet_projection import C0, C1, EDAY0, GROUPS, MAIL0, NCOLS, PROJ0
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


P = [r + [""] * (NCOLS - len(r)) for r in get(f"projection!A1:Q{C1}")]
Vd = [r + [""] * (60 - len(r)) for r in get(f"validations!A{FIRST}:BH{LAST}")]
num = lambda x: 0 if x == "" else x
cut = P[1][1]
n = bad = 0


def check(where, e, g):
    global n, bad
    n += 1
    ok = e == g or (isinstance(e, (int, float)) and isinstance(g, (int, float))
                    and abs(e - g) <= 1e-6 * max(1, abs(e)))
    if not ok:
        bad += 1
        if bad <= 8:
            print("MISMATCH", where, repr(e), repr(g))


recs = []
for k, v in enumerate(Vd):
    g = lambda c: v[col(c)]
    D = g("P")
    E = "" if D == "" else num(g("AI"))
    F = "" if D == "" else num(g("AJ"))
    G = g("Q")
    H = "" if D == "" or G == "" or num(G) == 0 else D / G
    I = "no Eday count" if H == "" else ("done" if H >= cut else "not done")
    J = "" if I == "no Eday count" else (0 if I == "done" else max(0, G - D))
    K = g("AE")
    Lm = "" if K == "" else num(g("AY"))
    M = "" if K == "" else num(g("AZ"))
    Nx = "" if K == "" else num(g("AF"))
    O = "" if K == "" else max(0, Nx - K)
    Pm = num(g("AQ")) - num(g("AR"))
    Q = num(g("U"))
    exp = [g("A"), g("C"), D, E, F, G, H, I, J, K, Lm, M, Nx, O, Pm, Q]
    row = P[C0 - 1 + k]
    got = [row[0], row[2]] + row[3:17]
    for j, (e, x) in enumerate(zip(exp, got)):
        check((g("C"), "detail", j), e, x)
    recs.append(dict(grp=g("A"), D=num(D), E=num(E), F=num(F), G=num(G), st=I, J=num(J),
                     K=num(K), L=num(Lm), M=num(M), N=num(Nx), O=num(O), P=Pm, Q=Q, hasK=K != ""))


def block(sub, kind, assumption=""):
    if kind == "eday":
        cov = [x for x in sub if x["st"] != "no Eday count"]
        B, C, D, E, J = (sum(x[k] for x in sub) for k in "DEFGJ")
        E = sum(x["G"] for x in cov)
    else:
        B, C, D, E, J = (sum(x[k] for x in sub) for k in "KLMNO")
    F = B / E if E else ""
    G = C / B if B > 0 else ""
    H = D / B if B > 0 else ""
    I = "" if G == "" else G - H
    if kind == "mail" and assumption != "":
        tw = 1 if G == "" else G + H
        K, L = J * tw * assumption, J * tw * (1 - assumption)
    else:
        K = "" if G == "" else J * G
        L = "" if H == "" else J * H
    Mc = "" if K == "" else K - L
    return [B, C, D, E, F, G, H, I, J, K, L, Mc]


mail_m, eday_m = {}, {}
for i, grp in enumerate(GROUPS):
    sub = [x for x in recs if x["grp"] == grp]
    mr, er = P[MAIL0 - 1 + i], P[EDAY0 - 1 + i]
    me = block(sub, "mail", mr[13])
    ee = block(sub, "eday")
    for j, e in enumerate(me):
        check((grp, "mail", j), e, mr[1 + j])
    for j, e in enumerate(ee):
        check((grp, "eday", j), e, er[1 + j])
    nc = sum(x["Q"] for x in sub if x["st"] == "no Eday count")
    check((grp, "eday not covered"), nc / sum(x["Q"] for x in sub), er[15])
    mail_m[grp], eday_m[grp] = num(me[11]), num(ee[11])
    pr = P[PROJ0 - 1 + i]
    cur = sum(x["P"] for x in sub)
    for j, e in enumerate([cur, eday_m[grp], mail_m[grp], cur + eday_m[grp] + mail_m[grp]]):
        check((grp, "proj", j), e, pr[1 + j])

tot = P[PROJ0 + 2]
cur = sum(x["P"] for x in recs)
for j, e in enumerate([cur, sum(eday_m.values()), sum(mail_m.values()),
                       cur + sum(eday_m.values()) + sum(mail_m.values())]):
    check(("Total", "proj", j), e, tot[1 + j])

print("error cells", [(i + 1, j) for i, r in enumerate(P) for j, x in enumerate(r) if str(x).startswith("#")][:5])
print("cells compared", n, "mismatches", bad)
