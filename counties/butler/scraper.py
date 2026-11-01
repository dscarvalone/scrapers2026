"""Butler County, OH election results by vote type.

Tries the summary XML first (party, IDs, timestamp, possibly a finer vote-type
split), then falls back to the summary CSV.

Usage:
    python -m counties.butler.scraper                  # download live feed
    python -m counties.butler.scraper --file x.csv     # parse a local XML or CSV
    python -m counties.butler.scraper --long           # one row per vote type
"""

import sys
from pathlib import Path

from common.ohio_enr import run

BASE = "https://liveresults.boe.ohio.gov/ENR/butlerohenr/24"
URLS = [f"{BASE}/summary_24.xml", f"{BASE}/summary_24.csv"]

if __name__ == "__main__":
    sys.exit(run("Butler", URLS, Path(__file__).resolve().parent / "output"))
