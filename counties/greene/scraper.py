"""Greene County, OH election results by vote type (Enhanced Voting).

Public results page (linked from the BOE site as "November 3, 2026 Election
Results"; found by the night-before recheck, 2026-11-03):
https://app.enhancedvoting.com/results/public/greene-county-oh/2026NovemberGeneral

Usage:
    python -m counties.greene.scraper
"""

import sys
from pathlib import Path

from common.enhanced_voting import run

JURISDICTION = "greene-county-oh"
ELECTION_ID = "2026NovemberGeneral"

if __name__ == "__main__":
    sys.exit(run("Greene", JURISDICTION, ELECTION_ID, Path(__file__).resolve().parent / "output"))
