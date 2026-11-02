"""Pickaway County, OH election results by vote type (Enhanced Voting).

Public results page (found by the 60-county survey, 2026-11-01):
https://app.enhancedvoting.com/results/public/pickaway-county-oh/GE2026_20261028170048
Vote groups: Election Day, In Office Absentee, Mail Absentee, Provisional.

Usage:
    python -m counties.pickaway.scraper
"""

import sys
from pathlib import Path

from common.enhanced_voting import run

JURISDICTION = "pickaway-county-oh"
ELECTION_ID = "GE2026_20261028170048"

if __name__ == "__main__":
    sys.exit(run("Pickaway", JURISDICTION, ELECTION_ID, Path(__file__).resolve().parent / "output"))
