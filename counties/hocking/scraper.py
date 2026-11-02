"""Hocking County, OH election results by vote type (Enhanced Voting).

Public results page (found by the 60-county survey, 2026-11-01):
https://app.enhancedvoting.com/results/public/hocking-county-oh/_20261013112017
Vote groups: Election Day, Early Voting, Absentee, Provisional.

Usage:
    python -m counties.hocking.scraper
"""

import sys
from pathlib import Path

from common.enhanced_voting import run

JURISDICTION = "hocking-county-oh"
ELECTION_ID = "_20261013112017"

if __name__ == "__main__":
    sys.exit(run("Hocking", JURISDICTION, ELECTION_ID, Path(__file__).resolve().parent / "output"))
