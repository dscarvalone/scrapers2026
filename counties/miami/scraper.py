"""Miami County, OH U.S. Senate results by vote type, from the county's
election-night PDF (Dominion results report).

Source (linked from the county BOE's election-results page; zero report
posted 2026-10-28): https://www.boe.ohio.gov/miami/c/elecres/20261103results.pdf
Columns: AB (absentee), ED (election day), EV (early vote), PR (provisional),
in the order printed in the report header. Not yet confirmed on a report
with real votes (see REPORT.md).

The BOE site is SOS-hosted and behind Cloudflare, so the PDF is fetched
through the Chrome window opened by tools/sos_chrome.sh.

Usage:
    python -m counties.miami.scraper
    python -m counties.miami.scraper --file results.pdf
"""

import argparse
import sys
from pathlib import Path

from common.pdf_results import run
from common.sos_browser import fetch_file_via_page

NEEDS_LOCAL_CHROME = True  # picked up by tools/run_sos_counties.py
URL = "https://www.boe.ohio.gov/miami/c/elecres/20261103results.pdf"
PAGE = "https://www.boe.ohio.gov/miami/election-info/election-results/"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    args = ap.parse_args(argv)
    data = Path(args.file).read_bytes() if args.file else fetch_file_via_page(URL, PAGE)
    return run("Miami", "dominion", data, Path(__file__).resolve().parent / "output", URL)


if __name__ == "__main__":
    sys.exit(main())
