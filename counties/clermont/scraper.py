"""Clermont County, OH U.S. Senate results by vote type, from the county's
results PDF ("Summary Results Report - Group Detail", Electionware).

The county posts its reports on its own site (boe.clermontcountyohio.gov,
plain HTTP, no Cloudflare). Before the election the results page links a
"Zero Report" (ZeroReport2026GEN.pdf, posted 2026-10-14). Its Senate block is
split: Election Day, Absentee Mail, Absentee In-Person, Provisional. The
positional parser was verified on it and on the county's May 2026 official
group-detail report with real votes (every row's columns sum to its total,
e.g. Acton 9,204 = 7,058 + 807 + 1,312 + 27).

The election-night file name isn't known in advance, so each run reads the
results page and takes the Nov 3, 2026 general-election results PDF it
links, preferring an unofficial/summary/group report over the zero report and
skipping precinct, SOVC, turnout and calendar files. With nothing newer than
the zero report it parses the zero report (all zeros).

Runs in tools/local_loop.sh (NEEDS_LOCAL_CHROME below is how
tools/run_sos_counties.py finds it; this scraper itself uses plain HTTP).

Usage:
    python -m counties.clermont.scraper
    python -m counties.clermont.scraper --file results.pdf
    python -m counties.clermont.scraper --url <direct PDF link>
"""

import argparse
import html
import re
import sys
from pathlib import Path
from urllib.parse import quote, urljoin

import requests

from common.pdf_results import run

NEEDS_LOCAL_CHROME = True  # picked up by tools/run_sos_counties.py (no Chrome needed)
RESULTS_PAGE = "https://boe.clermontcountyohio.gov/election_results/index.php"
ZERO_REPORT = "https://boe.clermontcountyohio.gov/ZeroReport2026GEN.pdf"
UA = {"User-Agent": "scrapers2026 (election results research)"}
NOV3 = re.compile(r"2026\s*gen|gen\w*\s*2026|nov(ember)?\.?\s*0?3,?\s*2026|11[-_/.]0?3[-_/.](20)?26", re.I)
SKIP = re.compile(r"precinct|sovc|turnout|ballots cast|calendar|overlap|canvass|write[- ]?in|populous", re.I)
PREFER = re.compile(r"unofficial|summary|group|result", re.I)
ZERO = re.compile(r"zero", re.I)


def pdf_links(page_html: str) -> list[tuple[str, str]]:
    out = []
    for href, label in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', page_html, re.I | re.S):
        url = urljoin(RESULTS_PAGE, html.unescape(href.strip()))
        if re.search(r"\.pdf(\?|$)", url, re.I):
            out.append((url, " ".join(html.unescape(re.sub(r"<[^>]+>", " ", label)).split())))
    return out


def pick(links: list[tuple[str, str]]) -> str | None:
    """Best Nov 3, 2026 results PDF: a non-zero summary first, else the zero report."""
    cands = [(u, l) for u, l in links if NOV3.search(f"{u} {l}") and not SKIP.search(f"{u} {l}")]
    real = [u for u, l in cands if not ZERO.search(f"{u} {l}")]
    real.sort(key=lambda u: not PREFER.search(u + " " + dict(cands)[u]))
    if real:
        return real[0]
    zero = [u for u, l in cands if ZERO.search(f"{u} {l}")]
    return zero[0] if zero else None


def get(url: str) -> requests.Response:
    # Links on the page contain spaces; encode the path but keep the query.
    base, _, query = url.partition("?")
    r = requests.get(quote(base, safe=":/%") + (f"?{query}" if query else ""), headers=UA, timeout=60)
    r.raise_for_status()
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--url")
    args = ap.parse_args(argv)
    out = Path(__file__).resolve().parent / "output"
    if args.file:
        return run("Clermont", "positional", Path(args.file).read_bytes(), out, args.file)
    url = args.url
    if not url:
        try:
            url = pick(pdf_links(get(RESULTS_PAGE).text))
        except requests.RequestException as e:
            print(f"Clermont: results page unavailable ({e}); trying the zero report URL", file=sys.stderr)
        url = url or ZERO_REPORT
    if ZERO.search(url):
        print("Clermont: no election-night report linked yet; parsing the zero report", file=sys.stderr)
    return run("Clermont", "positional", get(url).content, out, url)


if __name__ == "__main__":
    sys.exit(main())
