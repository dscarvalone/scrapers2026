"""Summit County, OH election results by vote type (Enhanced Voting).

Public results page (linked from the county BOE site; found 2026-11-01):
https://app.enhancedvoting.com/results/public/summit-county-oh/elections/Nov2026General

Vote groups: Abs Mail, Polls, Abs Walk-in, Provisional, Timely Abs.

Usage:
    python -m counties.summit.scraper
"""

import sys
from pathlib import Path

from common.enhanced_voting import run

JURISDICTION = "summit-county-oh"
ELECTION_ID = "Nov2026General"

if __name__ == "__main__":
    sys.exit(run("Summit", JURISDICTION, ELECTION_ID, Path(__file__).resolve().parent / "output"))
