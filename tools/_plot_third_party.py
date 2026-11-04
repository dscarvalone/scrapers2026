"""Plot: third-party Senate vote vs Dem 2-way share by county, AP numbers
('dscc data tab'). Left: all third-party (Redpath + Levy + other) as a share of
the county's total; right: Redpath and Levy separately. Bubble size = total
votes; color = group (projection tab). Lines = vote-weighted least squares.
Usage: python -m tools._plot_third_party <out.png>"""
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from tools.push_sheet import session
from tools.sheet_palette import COLORS
from tools.sheet_projection import C0, C1
from tools.sheet_validations import KEY

out = sys.argv[1]
s, _ = session(KEY)
b = 'https://sheets.googleapis.com/v4/spreadsheets/1jCzz-0RdSDOpIiAh_5Gx8RX5pahF6I2WstewfCAbuVs/values/'
g = lambda r: s.get(b + r, params={'valueRenderOption': 'UNFORMATTED_VALUE'}).json().get('values', [])
grp = {r[2]: r[0] for r in g(f'projection!A{C0}:C{C1}') if len(r) > 2}
h = g("'dscc data tab'!D6:ZZ6")[0]
num = lambda v: v if isinstance(v, (int, float)) else 0
pts, state = [], None
for r in g("'dscc data tab'!D7:ZZ100"):
    a = dict(zip(h, r))
    d, gp = num(a.get('dem_votes')), num(a.get('gop_votes'))
    b1, b2, o = num(a.get('breakout_1_votes')), num(a.get('breakout_2_votes')), num(a.get('other_votes'))
    tot = d + gp + b1 + b2 + o
    if not tot:
        continue
    p = dict(name=a['reporting_unit_name'], grp=grp.get(a['reporting_unit_name'], ''), tot=tot,
             tw=d / (d + gp), third=(b1 + b2 + o) / tot, red=b1 / tot, levy=b2 / tot, n3=b1 + b2 + o)
    if p['name'] == 'Statewide':
        state = p
    else:
        pts.append(p)


def wfit(x, y, w):
    x, y, w = map(np.asarray, (x, y, w))
    m, c = np.polyfit(x, y, 1, w=np.sqrt(w))
    yh = m * x + c
    ybar = np.average(y, weights=w)
    r2 = 1 - np.sum(w * (y - yh) ** 2) / np.sum(w * (y - ybar) ** 2)
    return m, c, r2


fig, (ax, ax2) = plt.subplots(1, 2, figsize=(16, 7.5), dpi=130)
size = lambda p: max(18, p['tot'] / 900)
pf = matplotlib.ticker.PercentFormatter(1.0, decimals=0)
pf1 = matplotlib.ticker.PercentFormatter(1.0, decimals=1)
X = [p['tw'] for p in pts]
xs = np.linspace(min(X) - 0.01, max(X) + 0.01, 50)

# Left: all third-party
for gname in ('base', 'swing', 'rurals'):
    P = [p for p in pts if p['grp'] == gname]
    ax.scatter([p['tw'] for p in P], [p['third'] for p in P], s=[size(p) for p in P], color=COLORS[gname],
               alpha=0.6, edgecolors='white', lw=0.8, label=gname, zorder=3)
m, c, r2 = wfit(X, [p['third'] for p in pts], [p['tot'] for p in pts])
ax.plot(xs, m * xs + c, color='#555', lw=1.3, zorder=2)
ax.text(0.98, 0.6, f'fit: R² {r2:.2f}, {10 * m:+.2f} pts third-party\nper +10 pts Brown 2-way', transform=ax.transAxes,
        ha='right', fontsize=9, color='#555')
ax.axhline(state['third'], color='#999', ls='--', lw=1)
ax.text(min(X) - 0.01, state['third'], f" statewide {100 * state['third']:.1f}%", va='bottom', fontsize=8.5,
        color='#666')
for p in sorted(pts, key=lambda p: -p['tot'])[:12] + sorted(pts, key=lambda p: -p['third'])[:5]:
    ax.annotate(p['name'].replace(' County', ''), (p['tw'], p['third']), xytext=(6, 3),
                textcoords='offset points', fontsize=8)
ax.xaxis.set_major_formatter(pf); ax.yaxis.set_major_formatter(pf1)
ax.set_xlabel('Brown 2-way share (AP)'); ax.set_ylabel('Third-party share of total vote (Redpath + Levy + other)')
ax.set_title('All third-party', fontsize=11)
ax.grid(alpha=0.25)
leg = ax.legend(loc='upper right', frameon=False, fontsize=9)
for hnd in leg.legend_handles: hnd.set_sizes([60])

# Right: Redpath vs Levy
for key, col, lab in (('red', '#d4a017', 'Redpath (Lib)'), ('levy', '#2a9d8f', 'Levy')):
    ax2.scatter(X, [p[key] for p in pts], s=[size(p) for p in pts], color=col, alpha=0.55,
                edgecolors='white', lw=0.8, label=f"{lab}: statewide {100 * state[key]:.2f}%", zorder=3)
    m2, c2, r22 = wfit(X, [p[key] for p in pts], [p['tot'] for p in pts])
    ax2.plot(xs, m2 * xs + c2, color=col, lw=1.3, zorder=2)
    ax2.text(xs[-1], m2 * xs[-1] + c2, f'  R² {r22:.2f}', fontsize=8.5, color=col, va='center')
ax2.xaxis.set_major_formatter(pf); ax2.yaxis.set_major_formatter(pf1)
ax2.set_xlabel('Brown 2-way share (AP)'); ax2.set_ylabel('Share of total vote')
ax2.set_title('Redpath vs Levy', fontsize=11)
for p in sorted(pts, key=lambda p: -p['levy'])[:2] + sorted(pts, key=lambda p: -p['red'])[:2]:
    for key in ('red', 'levy'):
        if p[key] == max(p['red'], p['levy']):
            ax2.annotate(p['name'].replace(' County', ''), (p['tw'], p[key]), xytext=(6, 3),
                         textcoords='offset points', fontsize=8)
ax2.grid(alpha=0.25)
leg2 = ax2.legend(loc='upper right', frameon=False, fontsize=9)
for hnd in leg2.legend_handles: hnd.set_sizes([60])

now = datetime.now(ZoneInfo('America/New_York')).strftime('%-I:%M %p')
fig.suptitle(f"{now} ET | AP county results, {len(pts)} counties | third-party "
             f"{state['n3']:,} votes ({100 * state['third']:.1f}%) | bubble = total votes, lines vote-weighted",
             fontsize=11.5)
fig.tight_layout(); fig.savefig(out)
print(out, len(pts), f"third {state['third']:.4f} red {state['red']:.4f} levy {state['levy']:.4f}")
print(f"fit all: slope {m:.4f} R2 {r2:.3f}")
for gname in ('base', 'swing', 'rurals'):
    P = [p for p in pts if p['grp'] == gname]
    w = sum(p['tot'] for p in P)
    print(f"  {gname:7} {len(P):2} third {100 * sum(p['third'] * p['tot'] for p in P) / w:.2f}%  "
          f"red {100 * sum(p['red'] * p['tot'] for p in P) / w:.2f}%  levy {100 * sum(p['levy'] * p['tot'] for p in P) / w:.2f}%  "
          f"2way {100 * sum(p['tw'] * p['tot'] for p in P) / w:.1f}")
for p in sorted(pts, key=lambda p: -p['third'])[:6]:
    print(f"  top {p['name']:20} third {100 * p['third']:.2f}%  2way {100 * p['tw']:.1f}  {p['tot']:,}")
for p in sorted(pts, key=lambda p: p['third'])[:4]:
    print(f"  low {p['name']:20} third {100 * p['third']:.2f}%  2way {100 * p['tw']:.1f}  {p['tot']:,}")
