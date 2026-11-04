"""How each itemized county's Election Day margin moved as its Eday count grew,
from the git history of counties/<c>/data/summary_wide.csv. Answers whether
the 'so far' Eday share is a fair basis for the outstanding Eday vote.
Usage: python -m tools._eday_drift county [county ...]"""
import csv
import io
import subprocess
import sys

from common import senate

ROOT = senate.COUNTIES_DIR.parent


def eday(text: str, county: str):
    """(eday total, Brown, Husted) from one version of the data file, using the
    same label mapping as the build (method buckets from common.senate)."""
    import tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False) as f:
        f.write(text)
    try:
        rows = senate.county_rows(county, Path(f.name))
    except Exception:
        return None
    finally:
        Path(f.name).unlink()
    ed = [r for r in rows if r['method'] == 'Election Day']
    tot = sum(int(r['votes']) for r in ed)
    d = sum(int(r['votes']) for r in ed if r['candidate'] == 'Sherrod Brown')
    g = sum(int(r['votes']) for r in ed if r['candidate'] == 'Jon Husted')
    return tot, d, g


for county in sys.argv[1:]:
    path = f'counties/{county}/data/summary_wide.csv'
    log = subprocess.run(['git', 'log', '--since=2026-11-03 19:30', '--format=%h %cd', '--date=format:%H:%M',
                          '--', path], capture_output=True, text=True, cwd=ROOT).stdout.split('\n')
    seen = []
    for line in reversed([l for l in log if l]):
        h, t = line.split()
        txt = subprocess.run(['git', 'show', f'{h}:{path}'], capture_output=True, text=True, cwd=ROOT).stdout
        r = eday(txt, county)
        if r and r[0] and (not seen or r[0] != seen[-1][1]):
            seen.append((t, *r))
    cur = open(ROOT / path).read()
    r = eday(cur, county)
    if r and r[0] and (not seen or r[0] != seen[-1][1]):
        seen.append(('now', *r))
    print(county)
    prev = None
    for t, tot, d, g in seen:
        inc = ''
        if prev and tot > prev[0]:
            dt, dd, dg = tot - prev[0], d - prev[1], g - prev[2]
            inc = f'   batch +{dt:,}: margin {100 * (dd - dg) / dt:+.1f}'
        print(f'  {t:>5} eday {tot:>8,}  cum margin {100 * (d - g) / tot:+.1f}{inc}')
        prev = (tot, d, g)
