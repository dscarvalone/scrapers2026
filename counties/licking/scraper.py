"""Licking County, OH U.S. Senate results by vote type, from the county's
election-night PDF (ES&S Electionware "Summary Report").

Source (linked from the county BOE's election-results page; zero report
posted 2026-10-30): https://www.boe.ohio.gov/licking/c/elecres/20261103results.pdf
Columns: Election Day, Absentee Office (early in-person), Absentee Mail,
Provisional. Order verified on the May 2026 report (columns sum to TOTAL).

The BOE site is SOS-hosted and behind Cloudflare, so the PDF is fetched
through the Chrome window opened by tools/sos_chrome.sh.

Usage:
    python -m counties.licking.scraper
    python -m counties.licking.scraper --file results.pdf
"""

import argparse
import sys
from pathlib import Path

from common.pdf_results import run
from common.sos_browser import fetch_file_via_page

NEEDS_LOCAL_CHROME = True  # picked up by tools/run_sos_counties.py
URL = "https://www.boe.ohio.gov/licking/c/elecres/20261103results.pdf"
PAGE = "https://www.boe.ohio.gov/licking/election-info/election-results/"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    args = ap.parse_args(argv)
    data = Path(args.file).read_bytes() if args.file else fetch_file_via_page(URL, PAGE)
    return run("Licking", "electionware", data, Path(__file__).resolve().parent / "output", URL)


if __name__ == "__main__":
    sys.exit(main())
