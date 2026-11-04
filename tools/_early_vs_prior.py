"""Early (EVIP + VBM) Dem 2-way: actual (our feed, 'methods' tab) vs the model's
expected early_exp_two_way ('dscc data tab'), county by county.
Itemized counties are the county's own split; first_drop is the SOS estimate.
Usage: python -m tools._early_vs_prior [out.png]"""
import sys

from tools.push_sheet import session
from tools.sheet_validations import KEY

s, _ = session(KEY)
b = 'https://sheets.googleapis.com/v4/spreadsheets/1jCzz-0RdSDOpIiAh_5Gx8RX5pahF6I2WstewfCAbuVs/values/'
g = lambda r: s.get(b + r, params={'valueRenderOption': 'UNFORMATTED_VALUE'}).json().get('values', [])
M = g('methods!A1:ZZ100')
mh = M[0]
meth = {r[mh.index('reporting_unit_name')]: dict(zip(mh, r + [''] * (len(mh) - len(r)))) for r in M[1:] if r}
h = g("'dscc data tab'!D6:ZZ6")[0]
ap = {r[0]: dict(zip(h, r)) for r in g("'dscc data tab'!D7:ZZ100") if r}
grp = {r[2]: r[0] for r in g('projection!A38:C125') if len(r) > 2}
n = lambda v: v if isinstance(v, (int, float)) else None

pts = []
for c, m in meth.items():
    if c == 'Statewide':
        continue
    d, gp = n(m.get('early_dem_votes')), n(m.get('early_gop_votes'))
    a = ap.get(c, {})
    e = n(a.get('early_exp_two_way'))
    if not d or not gp or e is None:
        continue
    rec = dict(c=c.replace(' County', ''), g=grp.get(c, ''), src=m['method_source'], act=d / (d + gp), exp=e,
               n=d + gp, cnt=n(m.get('early_total_votes')), expv=n(a.get('early_exp_total_votes')))
    for k in ('evip', 'vbm'):
        dd, gg = n(m.get(f'{k}_dem_votes')), n(m.get(f'{k}_gop_votes'))
        rec[k] = (dd / (dd + gg), dd + gg) if dd and gg else None
        rec[k + '_exp'] = n(a.get(f'{k}_exp_two_way'))
    pts.append(rec)


def summ(P, lab):
    if not P:
        return
    W = sum(p['n'] for p in P)
    wa = sum(p['act'] * p['n'] for p in P) / W
    we = sum(p['exp'] * p['n'] for p in P) / W
    up = sum(p['act'] > p['exp'] for p in P)
    print(f"{lab:24} {len(P):2} cty {W:>9,} votes  actual {100 * wa:.1f}  exp {100 * we:.1f}  "
          f"gap {100 * (wa - we):+.2f}  simple {100 * sum(p['act'] - p['exp'] for p in P) / len(P):+.2f}  "
          f"{up}/{len(P)} above")


I = [p for p in pts if p['src'] == 'itemized']
F = [p for p in pts if p['src'] == 'first_drop']
summ(I, 'ITEMIZED')
for x in ('base', 'swing', 'rurals'):
    summ([p for p in I if p['g'] == x], '  ' + x)
summ(F, 'FIRST-DROP (estimate)')
for x in ('base', 'swing', 'rurals'):
    summ([p for p in F if p['g'] == x], '  ' + x)
summ(pts, 'ALL')
for k in ('evip', 'vbm'):
    Q = [p for p in I if p[k] and p[k + '_exp'] is not None]
    if Q:
        W = sum(p[k][1] for p in Q)
        wa = sum(p[k][0] * p[k][1] for p in Q) / W
        we = sum(p[k + '_exp'] * p[k][1] for p in Q) / W
        print(f"{k.upper():24} {len(Q):2} cty {W:>9,} votes  actual {100 * wa:.1f}  exp {100 * we:.1f}  "
              f"gap {100 * (wa - we):+.2f}  {sum(p[k][0] > p[k + '_exp'] for p in Q)}/{len(Q)} above")
print('\nItemized, by votes:')
for p in sorted(I, key=lambda p: -p['n']):
    cov = f"{100 * p['cnt'] / p['expv']:.0f}%" if p['cnt'] and p['expv'] else ''
    print(f"  {p['g']:6} {p['c']:12} act {100 * p['act']:.1f} exp {100 * p['exp']:.1f} "
          f"gap {100 * (p['act'] - p['exp']):+.1f}  {p['n']:>7,}  early in {cov}")
print('\nFirst-drop, largest gaps:')
for p in sorted(F, key=lambda p: -abs(p['act'] - p['exp']))[:8]:
    print(f"  {p['g']:6} {p['c']:12} act {100 * p['act']:.1f} exp {100 * p['exp']:.1f} "
          f"gap {100 * (p['act'] - p['exp']):+.1f}  {p['n']:>7,}")

if len(sys.argv) > 1:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from tools.sheet_palette import COLORS
    fig, ax = plt.subplots(figsize=(10.5, 8), dpi=130)
    lo = min(min(p['act'], p['exp']) for p in pts) - 0.02
    hi = max(max(p['act'], p['exp']) for p in pts) + 0.02
    ax.plot([lo, hi], [lo, hi], color='#888', lw=1, ls='--', zorder=1)
    ax.text(0.97, 0.06, 'dashed line: actual = expected\ndots above it: Brown ahead of the model',
            transform=ax.transAxes, ha='right', color='#666', fontsize=9)
    for x in ('base', 'swing', 'rurals'):
        for src, mk in (('itemized', 'o'), ('first_drop', 'D')):
            P = [p for p in pts if p['g'] == x and p['src'] == src]
            if P:
                ax.scatter([p['exp'] for p in P], [p['act'] for p in P], s=[max(25, p['n'] / 250) for p in P],
                           marker=mk, color=COLORS[x], alpha=0.6, edgecolors='white', lw=0.8,
                           label=f"{x} ({'own split' if src == 'itemized' else 'SOS first-drop est.'})", zorder=3)
    for p in sorted(pts, key=lambda p: -p['n'])[:14] + sorted(pts, key=lambda p: -abs(p['act'] - p['exp']))[:4]:
        ax.annotate(f"{p['c']} {100 * (p['act'] - p['exp']):+.1f}", (p['exp'], p['act']), xytext=(6, 3),
                    textcoords='offset points', fontsize=8)
    W = sum(p['n'] for p in I)
    gi = sum((p['act'] - p['exp']) * p['n'] for p in I) / W
    pf = matplotlib.ticker.PercentFormatter(1.0, decimals=0)
    ax.xaxis.set_major_formatter(pf); ax.yaxis.set_major_formatter(pf)
    ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    ax.set_xlabel("Expected Early Brown 2-way (model early_exp_two_way)")
    ax.set_ylabel('Actual Early Brown 2-way (our feed, EVIP + VBM)')
    now = datetime.now(ZoneInfo('America/New_York')).strftime('%-I:%M %p')
    ax.set_title(f"{now} ET | Early actual vs expected, {len(pts)} counties | own-split counties "
                 f"({len(I)}): vote-weighted {100 * gi:+.1f} pts", fontsize=11)
    ax.grid(alpha=0.25)
    leg = ax.legend(loc='upper left', frameon=False, fontsize=8.5)
    for hnd in leg.legend_handles:
        hnd.set_sizes([50])
    fig.tight_layout()
    fig.savefig(sys.argv[1])
    print(sys.argv[1])
