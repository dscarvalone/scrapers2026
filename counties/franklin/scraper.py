"""Franklin County, OH election results by vote type.

Franklin runs its own copy of the Ohio ENR software at
liveresults.franklincountyohio.gov (not the SOS-hosted liveresults.boe.ohio.gov,
which blocks automated clients behind a Cloudflare challenge). Same summary
XML/CSV format, but with different vote-type tags (see common/ohio_enr.py).

Election ID 4 is the Nov 3, 2026 general (feed generated 2026-10-26, has the
U.S. Senate race). IDs 1-3 are earlier 2026 elections. Note the county's
vote.franklincountyohio.gov/elections page still links ID 1, so don't derive
the ID from that page.

Usage:
    python -m counties.franklin.scraper                  # download live feed
    python -m counties.franklin.scraper --file x.xml     # parse a local XML or CSV
    python -m counties.franklin.scraper --long           # one row per vote type
    python -m counties.franklin.scraper --url <url>      # override the source
"""

import sys
from pathlib import Path

from common.ohio_enr import run

ELECTION_ID = 4
BASE = f"https://liveresults.franklincountyohio.gov/enr/franklinohenr/{ELECTION_ID}"
URLS = [f"{BASE}/summary_{ELECTION_ID}.xml", f"{BASE}/summary_{ELECTION_ID}.csv"]

if __name__ == "__main__":
    sys.exit(run("Franklin", URLS, Path(__file__).resolve().parent / "output",
                 expect_year="2026"))
