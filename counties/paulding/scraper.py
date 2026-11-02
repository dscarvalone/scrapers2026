"""Paulding County, OH U.S. Senate results by vote type, from the county's
election-night PDF on its SOS-hosted BOE site.

Source: https://www.boe.ohio.gov/paulding/c/elecres/20261103results.pdf
(the zero report was already posted when checked on 2026-11-01)
Columns in the Senate block: Election Day, Absentee, Provisional.
Parsed by word position (common/pdf_results.parse_positional): each number is
assigned to the header printed above it. Verified against the county's
May 2026 report with real votes (every row's columns sum to its total).

Fetched through the Chrome window opened by tools/sos_chrome.sh.

Usage:
    python -m counties.paulding.scraper
    python -m counties.paulding.scraper --file results.pdf
"""

import argparse
import sys
from pathlib import Path

from common.pdf_results import run
from common.sos_browser import fetch_file_via_page

NEEDS_LOCAL_CHROME = True  # picked up by tools/run_sos_counties.py
URL = "https://www.boe.ohio.gov/paulding/c/elecres/20261103results.pdf"
PAGE = "https://www.boe.ohio.gov/paulding/election-info/election-results/"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    args = ap.parse_args(argv)
    data = Path(args.file).read_bytes() if args.file else fetch_file_via_page(URL, PAGE)
    return run("Paulding", "positional", data, Path(__file__).resolve().parent / "output", URL)


if __name__ == "__main__":
    sys.exit(main())
