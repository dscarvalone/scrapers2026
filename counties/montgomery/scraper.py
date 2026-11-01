"""Montgomery County, OH election results by vote type (Enhanced Voting).

Public results page:
https://app.enhancedvoting.com/results/public/Montgomery-County-OH/elections/2026NovemberGeneralElection
(linked from the county BOE's election-results page; found 2026-11-01).

Usage:
    python -m counties.montgomery.scraper
"""

import sys
from pathlib import Path

from common.enhanced_voting import run

JURISDICTION = "Montgomery-County-OH"
ELECTION_ID = "2026NovemberGeneralElection"

if __name__ == "__main__":
    sys.exit(run("Montgomery", JURISDICTION, ELECTION_ID, Path(__file__).resolve().parent / "output"))
