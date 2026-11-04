"""Cuyahoga County, OH election results by vote type (Enhanced Voting live API).

Source: Enhanced Voting's public results API, jurisdiction cuyahoga-county-oh,
election GE2026 (found 2026-11-03 8 PM; the same API Summit / Montgomery /
Greene use):
    https://app.enhancedvoting.com/results/public/api/elections/cuyahoga-county-oh/GE2026/data

Vote groups: Election Day, Early In-Person, Vote By Mail, Provisional,
Post Election Day, Post VBM.

This replaces the earlier source, a fixed "All Results" .xlsx export
(app.enhancedvoting.com/cdn/results/6397b9a7-.../All Results_6c376c4d-....xlsx),
which stayed at the zero report on election night: every run "succeeded" with
zeros while the live site had 153k votes.

Usage:
    python -m counties.cuyahoga.scraper
"""

import sys
from pathlib import Path

from common.enhanced_voting import run

JURISDICTION = "cuyahoga-county-oh"
ELECTION_ID = "GE2026"

if __name__ == "__main__":
    sys.exit(run("Cuyahoga", JURISDICTION, ELECTION_ID, Path(__file__).resolve().parent / "output"))
