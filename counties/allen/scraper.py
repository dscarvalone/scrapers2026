"""Allen County, OH U.S. Senate results by vote type, from the county's
election-night "Unofficial" PDF.

Allen posts election-night results as a link on its BOE site
(allen.boe.ohio.gov, results category), usually to Dropbox. The Nov 4, 2025
unofficial report was an ES&S summary with TOTAL, Election Day, Absentee,
Provisional per candidate (parser verified on it: e.g. 353 = 302 + 51 + 0).
The Nov 3, 2026 link won't exist until results are posted, so each run:

  1. reads the results page (and a Nov 3 post it links to, if any) for a
     link whose text or URL says November 3, 2026 and Unofficial (skipping
     overlap / precinct / audit reports)
  2. downloads it (Dropbox: plain HTTP with dl=1; SOS-hosted: through the
     Chrome window opened by tools/sos_chrome.sh)
  3. parses the U.S. Senate race (common/pdf_results.py, ess_summary layout)

Until the link appears it prints "not posted yet" and writes nothing.

Usage:
    python -m counties.allen.scraper
    python -m counties.allen.scraper --file results.pdf
    python -m counties.allen.scraper --url <direct PDF or Dropbox link>
"""

import argparse
import html
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from common.pdf_results import run

NEEDS_LOCAL_CHROME = True  # picked up by tools/run_sos_counties.py
RESULTS_PAGE = "https://allen.boe.ohio.gov/category/election-results/"
UA = {"User-Agent": "scrapers2026 (election results research)"}
NOV3 = re.compile(r"nov(ember)?\.?\s*0?3,?\s*2026|11[-_/.]0?3[-_/.](20)?26|2026[-_ ]?gen(eral)?", re.I)
UNOFFICIAL = re.compile(r"unofficial", re.I)
SKIP = re.compile(r"overlap|precinct|audit|sovc|statement of votes|populous|canvass", re.I)


def get_page(url: str) -> str:
    """Plain HTTP first; the Chrome window if Cloudflare refuses."""
    from tools.survey_counties import Fetcher
    f = Fetcher()
    try:
        _, text, _ = f.page(url)
        return text
    finally:
        f.close()


def links(page_html: str, base: str) -> list[tuple[str, str]]:
    out = []
    for href, label in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', page_html, re.I | re.S):
        out.append((urljoin(base, html.unescape(href.strip())),
                    html.unescape(re.sub(r"<[^>]+>|\s+", " ", label)).strip()))
    return out


def find_report() -> str | None:
    page = get_page(RESULTS_PAGE)
    candidates, posts = [], []
    for url, label in links(page, RESULTS_PAGE):
        blob = f"{url} {label}"
        if not NOV3.search(blob) or SKIP.search(blob):
            continue
        if re.search(r"dropbox\.com|\.pdf(\?|$)", url, re.I) and UNOFFICIAL.search(blob):
            candidates.append(url)
        elif urlparse(url).netloc.endswith("allen.boe.ohio.gov"):
            posts.append(url)
    for post in posts[:2]:  # election-night posts hold the actual links
        for url, label in links(get_page(post), post):
            blob = f"{url} {label}"
            if re.search(r"dropbox\.com|\.pdf(\?|$)", url, re.I) and UNOFFICIAL.search(blob) and not SKIP.search(blob):
                candidates.append(url)
    return candidates[0] if candidates else None


def download(url: str) -> bytes:
    if "dropbox.com" in url:
        url = re.sub(r"([?&])dl=0", r"\1dl=1", url)
        if "dl=1" not in url:
            url += ("&" if "?" in url else "?") + "dl=1"
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        return r.content
    if "boe.ohio.gov" in urlparse(url).netloc:
        from common.sos_browser import fetch_file_via_page
        return fetch_file_via_page(url, RESULTS_PAGE if "allen.boe" in url else url.rsplit("/", 1)[0] + "/")
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.content


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--url")
    args = ap.parse_args(argv)
    out = Path(__file__).resolve().parent / "output"
    if args.file:
        return run("Allen", "positional", Path(args.file).read_bytes(), out, args.file)
    url = args.url or find_report()
    if not url:
        print("Allen: Nov 3, 2026 unofficial results not posted yet", file=sys.stderr)
        return 0
    return run("Allen", "positional", download(url), out, url)


if __name__ == "__main__":
    sys.exit(main())
