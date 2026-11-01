"""Hamilton County, OH election results by vote type (Clarity / Scytl).

Results site (pointed out by the owner, 2026-11-01):
https://results.votehamiltoncountyohio.gov/OH/Hamilton/127473/web.345435/#/detail/8
Data: <base>/current_ver.txt, then <base>/<ver>/reports/detailxml.zip.
Vote types: Election, Early.

Usage:
    python -m counties.hamilton.scraper
    python -m counties.hamilton.scraper --file detail.xml
"""

import sys
from pathlib import Path

from common.clarity import run

BASE = "https://results.votehamiltoncountyohio.gov/OH/Hamilton/127473"

if __name__ == "__main__":
    sys.exit(run("Hamilton", BASE, Path(__file__).resolve().parent / "output"))
