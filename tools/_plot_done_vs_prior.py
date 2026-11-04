"""Plot: counties 'done' in the projection tab (Eday >= cutoff of expected) -
AP actual Dem 2-way (dscc data tab two_way, Topline AK) vs the model's frozen
prior (expected_frozen_two_way, AJ). Hollow circles = our feed where it differs.
Usage: python -m tools._plot_done_vs_prior <out.png>"""
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tools.push_sheet import session
from tools.sheet_validations import KEY
from tools.sheet_projection import C0, C1, COL
from tools.sheet_palette import COLORS

out = sys.argv[1]
s, _ = session(KEY)
b = 'https://sheets.googleapis.com/v4/spreadsheets/1jCzz-0RdSDOpIiAh_5Gx8RX5pahF6I2WstewfCAbuVs/values/'
g = lambda r: s.get(b + r, params={'valueRenderOption': 'UNFORMATTED_VALUE'}).json().get('values', [])
D = [r + [''] * 40 for r in g(f'projection!A{C0}:AK{C1}')]
h = g("'dscc data tab'!D6:ZZ6")[0]
A = {r[0]: dict(zip(h, r)) for r in g("'dscc data tab'!D7:ZZ100") if r}
pts = []
for r in D:
    if r[COL['Eday status']] != 'done':
        continue
    a = A[r[2]]
    d, gp = r[COL['Dem total']], r[COL['Rep total']]
    pts.append((r[0], r[2].replace(' County', ''), a['expected_frozen_two_way'], a['two_way'], d / (d + gp),
                (a.get('dem_votes') or 0) + (a.get('gop_votes') or 0)))
fig, ax = plt.subplots(figsize=(10.5, 7.5), dpi=130)
lo = min(min(p[2], p[3], p[4]) for p in pts) - 0.03
hi = max(max(p[2], p[3], p[4]) for p in pts) + 0.03
ax.plot([lo, hi], [lo, hi], color='#888', lw=1, ls='--', zorder=1)
ax.text(hi - 0.005, hi - 0.02, 'actual = prior', ha='right', color='#666', fontsize=9)
for grp in ('base', 'swing', 'rurals'):
    P = [p for p in pts if p[0] == grp]
    if P:
        ax.scatter([p[2] for p in P], [p[3] for p in P], s=[max(30, p[5] / 120) for p in P], color=COLORS[grp],
                   alpha=0.65, edgecolors='white', lw=0.8, label=f'{grp} (AP actual)', zorder=3)
for grp, c, fz, ap, ours, n in pts:
    if abs(ap - ours) > 0.005:
        ax.plot([fz, fz], [ours, ap], color='#999', lw=0.8, zorder=2)
        ax.scatter([fz], [ours], s=40, facecolors='none', edgecolors=COLORS[grp], lw=1.2, zorder=3)
    ax.annotate(f'{c} {100 * (ap - fz):+.1f}', (fz, ap), xytext=(7, 3), textcoords='offset points', fontsize=8.5)
W = sum(p[5] for p in pts)
dw = sum((p[3] - p[2]) * p[5] for p in pts) / W
ax.scatter([], [], s=40, facecolors='none', edgecolors='#555', label='our feed (where it differs from AP)')
ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
pf = matplotlib.ticker.PercentFormatter(1.0)
ax.xaxis.set_major_formatter(pf); ax.yaxis.set_major_formatter(pf)
ax.set_xlabel('Expected Frozen Dem 2-Way Share (column AJ, model pre-election)')
ax.set_ylabel('Actual Dem 2-Way Share (column AK, AP)')
now = datetime.now(ZoneInfo('America/New_York')).strftime('%-I:%M %p')
ax.set_title(f'{now} | counties at 90%+ of expected Eday ({len(pts)}): actual vs frozen prior | '
             f'vote-weighted gap {100 * dw:+.1f} pts', fontsize=11)
ax.grid(alpha=0.25); ax.legend(loc='upper left', frameon=False, fontsize=9)
fig.tight_layout(); fig.savefig(out)
print(out, len(pts), f'{100 * dw:+.2f}', 'above', sum(p[3] > p[2] for p in pts), 'votes', W)
for grp in ('base', 'swing', 'rurals'):
    G = [p for p in pts if p[0] == grp]
    if G:
        w = sum(p[5] for p in G)
        print(f'  {grp:7} {len(G):2} counties  weighted {100 * sum((p[3] - p[2]) * p[5] for p in G) / w:+.2f}  ({w:,} votes)')
for p in sorted(pts, key=lambda x: -x[5]):
    print(f'  {p[0]:7} {p[1]:11} prior {p[2] * 100:.1f}  AP {p[3] * 100:.1f}  ours {p[4] * 100:.1f}  diff {100 * (p[3] - p[2]):+.1f}  {p[5]:,}')
