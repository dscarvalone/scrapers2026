"""Hamilton County, OH election results by vote type (Clarity / Scytl).

Results site (pointed out by the owner, 2026-11-01):
https://results.votehamiltoncountyohio.gov/OH/Hamilton/127473/web.345435/#/detail/8
Data: <base>/current_ver.txt, then <base>/<ver>/reports/detailxml.zip.
Vote types: Election, Early (no provisional column).

Runs in tools/local_loop.sh, NOT in GitHub Actions: the results host
(Scytl, behind Amazon CloudFront) answers GitHub's runners with an empty
current_ver.txt (manual Actions run, 2026-11-02), while plain HTTP from a
desktop gets the version number and the file. NEEDS_LOCAL_CHROME below is how
tools/run_sos_counties.py finds it; this scraper itself uses plain HTTP.

Usage:
    python -m counties.hamilton.scraper
    python -m counties.hamilton.scraper --file detail.xml
"""

import sys
from pathlib import Path

from common.clarity import run

NEEDS_LOCAL_CHROME = True  # picked up by tools/run_sos_counties.py (no Chrome needed)
BASE = "https://results.votehamiltoncountyohio.gov/OH/Hamilton/127473"


def main(argv=None) -> int:
    return run("Hamilton", BASE, Path(__file__).resolve().parent / "output", argv)


if __name__ == "__main__":
    sys.exit(main())
