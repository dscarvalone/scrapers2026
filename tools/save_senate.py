"""Save a county's latest scraper output to its committed data file, U.S.
Senate race only (common.senate.save_senate_only).

Used by the Actions workflow and tools/run_sos_counties.py in place of a
plain copy, so the repo holds Senate rows only. The scraper's own
output/ files (git-ignored, local) still have the whole feed.

Usage:
    python -m tools.save_senate <county> [<county> ...]   # output/summary_wide_latest.csv -> data/summary_wide.csv
    python -m tools.save_senate --all                     # re-filter every committed data file in place
"""

from __future__ import annotations

import sys
from pathlib import Path

from common.senate import COUNTIES_DIR, save_senate_only


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args == ["--all"]:
        jobs = [(p, p) for p in sorted(COUNTIES_DIR.glob("*/data/summary_wide.csv"))]
    else:
        jobs = [(COUNTIES_DIR / c / "output" / "summary_wide_latest.csv",
                 COUNTIES_DIR / c / "data" / "summary_wide.csv") for c in args]
    if not jobs:
        print(__doc__, file=sys.stderr)
        return 2
    failed = 0
    for src, dst in jobs:
        try:
            n = save_senate_only(src, dst)
            print(f"{dst.relative_to(COUNTIES_DIR.parent)}: {n} Senate rows", file=sys.stderr)
        except Exception as e:
            failed += 1
            print(f"ERROR {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
