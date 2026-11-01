"""Warren County, OH election results by vote type.

Usage:
    python -m counties.warren.scraper              # download live XML
    python -m counties.warren.scraper --file x.xml # parse a local copy
    python -m counties.warren.scraper --long       # one row per vote type
"""

import sys
from pathlib import Path

from common.ohio_enr import run

URL = "https://liveresults.boe.ohio.gov/ENR/warrenohenr/18/summary_18.xml"

if __name__ == "__main__":
    sys.exit(run("Warren", URL, Path(__file__).resolve().parent / "output"))
