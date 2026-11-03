"""Fetch one document from an SOS-hosted county site through the scrapers2026
Chrome window (tools/sos_chrome.sh), for checking a file by hand.

Usage: python -m tools.fetch_sos_doc <landing page URL> <document URL> <out path>
"""
import sys

from tools.survey_counties import Fetcher


def main(argv=None) -> int:
    landing, url, out = (argv or sys.argv[1:])[:3]
    f = Fetcher()
    try:
        f.page(landing)  # same-origin first, so the in-tab fetch is not cross-site
        st, ct, data, via = f.doc(url)
        print(st, ct, len(data), via)
        with open(out, "wb") as fh:
            fh.write(data)
    finally:
        f.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
