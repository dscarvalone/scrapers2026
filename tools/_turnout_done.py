"""Turnout in 'done' counties (projection tab Eday status = done): votes counted
vs the model's expected votes, overall and by mode, against Brown 2-way share.
Counted: our feed total_votes and Eday/Early split
('methods'). Expected: expected_frozen_total_votes (pre-election), and
eday/early_exp_total_votes for the modes.
Usage: python -m tools._turnout_done [out.png]"""
import sys

from tools.push_sheet import session
from tools.sheet_projection import C0, C1, COL
from tools.sheet_validations import KEY

s, _ = session(KEY)
b = 'https://sheets.googleapis.com/v4/spreadsheets/1jCzz-0RdSDOpIiAh_5Gx8RX5pahF6I2WstewfCAbuVs/values/'
g = lambda r: s.get(b + r, params={'valueRenderOption': 'UNFORMATTED_VALUE'}).json().get('values', [])
n = lambda v: v if isinstance(v, (int, float)) else None
D = [r + [''] * 40 for r in g(f'projection!A{C0}:AK{C1}')]
h = g("'dscc data tab'!D6:ZZ6")[0]
ap = {r[0]: dict(zip(h, r)) for r in g("'dscc data tab'!D7:ZZ100") if r}
M = g('methods!A1:ZZ100')
mh = M[0]
meth = {r[mh.index('reporting_unit_name')]: dict(zip(mh, r + [''] * (len(mh) - len(r)))) for r in M[1:] if r}

pts = []
for r in D:
    if r[COL['Eday status']] != 'done':
        continue
    c = r[2]
    a, m = ap[c], meth.get(c, {})
    d, gp = n(a.get('dem_votes')) or 0, n(a.get('gop_votes')) or 0
    # Counted = our feed (the same numbers "done" is judged on); AP lags in some counties.
    p = dict(c=c.replace(' County', ''), g=r[0], tot=n(m.get('total_votes')) or 0, ap=n(a.get('total_votes')) or 0,
             expf=n(a.get('expected_frozen_total_votes')), expl=n(a.get('exp_total_votes')),
             tw=d / (d + gp), fz=n(a.get('expected_frozen_two_way')), margin=d - gp,
             ed=n(m.get('eday_total_votes')), ea=n(m.get('early_total_votes')),
             ed_x=n(a.get('eday_exp_total_votes')), ea_x=n(a.get('early_exp_total_votes')),
             src=m.get('method_source', ''))
    p['ratio'] = p['tot'] / p['expf'] if p['expf'] else None
    pts.append(p)
pts = [p for p in pts if p['ratio']]


def agg(P, lab):
    if not P:
        return
    T, X = sum(p['tot'] for p in P), sum(p['expf'] for p in P)
    E = [p for p in P if p['ed'] is not None and p['ed_x']]
    A = [p for p in P if p['ea'] is not None and p['ea_x']]
    ed = sum(p['ed'] for p in E) / sum(p['ed_x'] for p in E) if E else float('nan')
    ea = sum(p['ea'] for p in A) / sum(p['ea_x'] for p in A) if A else float('nan')
    d = sum(p['tw'] * (p['tot']) for p in P) / T
    print(f"{lab:8} {len(P):2} cty  counted {T:>9,} / expected {X:>9,} = {100 * T / X:5.1f}%  "
          f"(Eday {100 * ed:5.1f}%, Early {100 * ea:5.1f}%)  Brown 2-way {100 * d:.1f}")


agg(pts, 'ALL')
for x in ('base', 'swing', 'rurals'):
    agg([p for p in pts if p['g'] == x], x)
# turnout vs partisanship: does over/under-turnout line up with Brown share?
import numpy as np
X = np.array([p['tw'] for p in pts]); Y = np.array([p['ratio'] for p in pts]); W = np.array([p['expf'] for p in pts])
m_, c_ = np.polyfit(X, Y, 1, w=np.sqrt(W))
r = np.corrcoef(X, Y)[0, 1]
print(f"fit: turnout ratio = {c_:.3f} + {m_:.3f} x Brown2way  (r {r:+.2f}; +10 pts Brown -> {10 * m_:+.1f} pts turnout)")
# what the turnout difference is worth: votes above/below expected at the county's own margin
net = sum((p['tot'] - p['expf']) * (p['margin'] / p['tot']) for p in pts)
print(f"net Dem votes from turnout vs expected (at each county's own margin): {net:+,.0f}")
print('\nby county (sorted by Brown 2-way):')
for p in sorted(pts, key=lambda p: -p['tw']):
    edr = f"{100 * p['ed'] / p['ed_x']:.0f}%" if p['ed'] is not None and p['ed_x'] else '-'
    ear = f"{100 * p['ea'] / p['ea_x']:.0f}%" if p['ea'] is not None and p['ea_x'] else '-'
    print(f"  {p['g']:6} {p['c']:12} Brown {100 * p['tw']:.1f}  counted {p['tot']:>8,} exp {p['expf']:>8,.0f} "
          f"= {100 * p['ratio']:5.1f}%  Eday {edr:>5} Early {ear:>5}  {p['src']}")

if len(sys.argv) > 1:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from tools.sheet_palette import COLORS
    fig, ax = plt.subplots(figsize=(10.5, 7.5), dpi=130)
    for x in ('base', 'swing', 'rurals'):
        P = [p for p in pts if p['g'] == x]
        ax.scatter([p['tw'] for p in P], [p['ratio'] for p in P], s=[max(30, p['expf'] / 600) for p in P],
                   color=COLORS[x], alpha=0.6, edgecolors='white', lw=0.8, label=x, zorder=3)
    xs = np.linspace(X.min() - 0.02, X.max() + 0.02, 20)
    ax.plot(xs, c_ + m_ * xs, color='#555', lw=1.2, zorder=2)
    ax.axhline(1, color='#888', ls='--', lw=1)
    T, XX = sum(p['tot'] for p in pts), sum(p['expf'] for p in pts)
    ax.axhline(T / XX, color='#555', ls=':', lw=1)
    ax.text(X.min() - 0.02, T / XX, f' all done counties {100 * T / XX:.1f}%', va='bottom', fontsize=8.5, color='#555')
    for p in sorted(pts, key=lambda p: -p['expf'])[:12] + sorted(pts, key=lambda p: -abs(p['ratio'] - 1))[:4]:
        ax.annotate(f"{p['c']} {100 * p['ratio']:.0f}%", (p['tw'], p['ratio']), xytext=(6, 3),
                    textcoords='offset points', fontsize=8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel('Brown 2-way share (AP)')
    ax.set_ylabel('Votes counted / expected (expected_frozen_total_votes)')
    now = datetime.now(ZoneInfo('America/New_York')).strftime('%-I:%M %p')
    ax.set_title(f"{now} ET | turnout vs expected in done counties ({len(pts)}) | "
                 f"+10 pts Brown share -> {10 * m_:+.1f} pts turnout (r {r:+.2f})", fontsize=11)
    ax.grid(alpha=0.25)
    leg = ax.legend(loc='upper left', frameon=False, fontsize=9)
    for hnd in leg.legend_handles:
        hnd.set_sizes([50])
    fig.tight_layout()
    fig.savefig(sys.argv[1])
    print(sys.argv[1])
