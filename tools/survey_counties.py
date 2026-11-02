"""Survey where a county publishes Nov 3, 2026 results and whether that
source splits the U.S. Senate vote by method.

For each county: open its official BOE site (counties.csv boe_url, from the
SOS directory), follow up to MAX_PAGES results-looking pages on the same
site, and collect:
  - links that look like Nov 3, 2026 results (2026 + Nov/11/General, or
    /20261103), and
  - links to known live-results hosts.
Each such document is then fetched and inspected:
  - PDF: text-extracted; does it contain the U.S. Senate race, and which
    vote-type column words appear in it
  - XLSX/CSV/HTML: the same checks on the text

Fetching: plain HTTP first. If that's refused (Cloudflare), the page is
loaded or fetched in a tab of the owner's Chrome window (tools/sos_chrome.sh).
The tab is opened by this script and closed after each county; the
owner's own tabs aren't touched. About 2 s between requests.

Output: tools/county_survey.json, written after every county (a rerun skips
counties already done; --redo to rescan).

Usage:
    python -m tools.survey_counties Hamilton Summit ...
"""

from __future__ import annotations

import argparse
import base64
import html as htmlmod
import os
import csv
import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("SURVEY_OUT", ROOT / "tools" / "county_survey.json"))
UA = {"User-Agent": "scrapers2026 (election results research)"}
PAUSE = float(os.environ.get("SURVEY_PAUSE", "2.0"))
MAX_PAGES = 4
MAX_DOCS = 6

RESULTS_WORDS = re.compile(r"result|election[-_ ]?night|election[-_ ]?info|unofficial|current[-_ ]?election", re.I)
NOV = re.compile(r"(20261103|11[-_/.]?0?3[-_/.]?(20)?26|nov(ember)?[-_ .]*0?3[-_ ,]*2026|2026[-_ ]*(general|nov))", re.I)
LIVE_HOSTS = re.compile(r"liveresults|enhancedvoting|clarityelections|clarity|electionstats|livevoterturnout|"
                        r"electionresults|results\.enr|scytl|votecount|electionnight|^results\.|/OH/[A-Za-z_]+/\d{5,}", re.I)
SENATE = re.compile(r"(u\.?\s*s\.?|united\s+states)\s+senat", re.I)
METHOD_WORDS = ["Election Day", "Absentee", "Early", "Mail", "Provisional", "Polls", "In Person",
                "In-Person", "Walk", "Vote by Mail", "Precinct", "Total"]
JS_FETCH = """async u=>{const r=await fetch(u,{cache:'no-store'});const b=new Uint8Array(await r.arrayBuffer());
let s='';for(let i=0;i<b.length;i+=8192)s+=String.fromCharCode.apply(null,b.subarray(i,i+8192));
return {s:r.status,t:r.headers.get('content-type')||'',b:btoa(s)}}"""


def is_block(status: int, text: str) -> bool:
    t = text[:5000].lower()
    return status in (403, 429, 503) and ("cloudflare" in t or "just a moment" in t or "security check" in t
                                           or "attention required" in t or "website maintenance" in t)


class Fetcher:
    def __init__(self):
        self.pw = self.browser = self.tab = None
        self.last: dict[str, float] = {}

    def _pace(self, host):
        w = PAUSE - (time.monotonic() - self.last.get(host, 0))
        if w > 0:
            time.sleep(w)
        self.last[host] = time.monotonic()

    def _tab(self):
        if self.tab is None:
            # One Playwright connection per process (common.sos_browser.shared):
            # Playwright's sync API refuses a second one in the same process.
            from common.sos_browser import shared
            self.tab = shared()._browser.contexts[0].new_page()
        return self.tab

    def close(self):
        try:
            if self.tab:
                self.tab.close()   # our own tab only; the shared connection stays
        except Exception:
            pass
        self.tab = None

    def page(self, url: str) -> tuple[str, str, str]:
        """(final_url, html, via) for an HTML page."""
        host = urlparse(url).netloc
        self._pace(host)
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.ok and not is_block(r.status_code, r.text):
                return r.url, r.text, "http"
            blocked = is_block(r.status_code, r.text)
        except Exception:
            blocked = True
        if not blocked:
            return url, "", "http-error"
        tab = self._tab()
        self._pace(host)
        tab.goto(url, timeout=45_000)
        for _ in range(15):
            if not is_block(403, tab.content()):
                break
            time.sleep(1)
        return tab.url, tab.content(), "chrome"

    def doc(self, url: str) -> tuple[int, str, bytes, str]:
        host = urlparse(url).netloc
        self._pace(host)
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.ok and not is_block(r.status_code, r.text[:5000] if "html" in r.headers.get("content-type", "") else ""):
                return r.status_code, r.headers.get("content-type", ""), r.content, "http"
        except Exception:
            pass
        tab = self._tab()
        if urlparse(tab.url).netloc != host:  # same-origin fetch needs a page on that host
            self._pace(host)
            tab.goto(f"{urlparse(url).scheme}://{host}/", timeout=45_000)
            time.sleep(2)
        self._pace(host)
        res = tab.evaluate(JS_FETCH, url)
        for wait in (60, 120):
            if res["s"] != 429:
                break
            print(f"429 on {url}; waiting {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)
            res = tab.evaluate(JS_FETCH, url)
        return res["s"], res["t"], base64.b64decode(res["b"]), "chrome"


def text_of(ctype: str, data: bytes) -> str:
    if data[:4] == b"%PDF":
        from pypdf import PdfReader
        try:
            return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
        except Exception as e:
            return f"(pdf text extraction failed: {e})"
    if data[:2] == b"PK":  # xlsx
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            return "\n".join(" | ".join(str(c) for c in row if c is not None)
                             for ws in wb.worksheets for row in ws.iter_rows(values_only=True))
        except Exception as e:
            return f"(xlsx read failed: {e})"
    t = data.decode("utf-8", "ignore")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<(script|style).*?</\1>", " ", t)))


def inspect(text: str) -> dict:
    m = SENATE.search(text)
    window = text[max(0, m.start() - 1500): m.start() + 2500] if m else ""
    return {
        "has_senate": bool(m),
        "has_husted": "Husted" in text,
        "method_words_near_senate": [w for w in METHOD_WORDS if w.lower() in window.lower()],
        "method_words_anywhere": [w for w in METHOD_WORDS if w.lower() in text.lower()],
        "senate_excerpt": re.sub(r"\s+", " ", window)[:700],
        "chars": len(text),
    }


def survey(f: Fetcher, county: str, boe_url: str) -> dict:
    rec = {"county": county, "boe_url": boe_url, "pages": [], "nov_links": [], "live_links": [], "docs": []}
    site = urlparse(boe_url).netloc.lower().removeprefix("www.")
    queue, seen = [boe_url], set()
    while queue and len(rec["pages"]) < MAX_PAGES:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        try:
            final, html, via = f.page(u)
        except Exception as e:
            rec["pages"].append({"url": u, "error": str(e)[:200]})
            continue
        rec["pages"].append({"url": final, "via": via, "chars": len(html)})
        for href, label in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            link = urljoin(final, htmlmod.unescape(href.strip()))
            label = htmlmod.unescape(re.sub(r"<[^>]+>|\s+", " ", label)).strip()[:80]
            p = urlparse(link)
            if p.scheme not in ("http", "https"):
                continue
            if LIVE_HOSTS.search(p.netloc + p.path) and "voterview" not in p.netloc:
                rec["live_links"].append({"url": link, "label": label})
            if NOV.search(link) or NOV.search(label):
                rec["nov_links"].append({"url": link, "label": label})
            same = p.netloc.lower().removeprefix("www.") == site
            if same and RESULTS_WORDS.search(p.path + " " + label) and not re.search(r"\.(pdf|xlsx?|csv|docx?)$", p.path, re.I):
                queue.append(link.split("#")[0])
    # Dedupe and inspect candidate documents
    cands, done = [], set()
    for l in rec["nov_links"] + rec["live_links"]:
        if l["url"] not in done:
            done.add(l["url"])
            cands.append(l)
    for l in cands[:MAX_DOCS]:
        try:
            status, ctype, data, via = f.doc(l["url"])
            info = {"url": l["url"], "label": l["label"], "status": status, "type": ctype[:40],
                    "bytes": len(data), "via": via}
            if status == 200:
                info.update(inspect(text_of(ctype, data)))
        except Exception as e:
            info = {"url": l["url"], "label": l["label"], "error": str(e)[:200]}
        rec["docs"].append(info)
    rec["live_links"] = rec["live_links"][:15]
    rec["nov_links"] = rec["nov_links"][:15]
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("counties", nargs="+")
    ap.add_argument("--redo", action="store_true")
    args = ap.parse_args(argv)
    boe = {r["county"]: r["boe_url"] for r in csv.DictReader((ROOT / "counties.csv").open())}
    done = json.loads(OUT.read_text()) if OUT.exists() else {}
    for n, county in enumerate(args.counties, 1):
        if county in done and not args.redo:
            continue
        f = Fetcher()
        try:
            rec = survey(f, county, boe[county])
        finally:
            f.close()   # fresh Chrome connection per county (connections drop over time)
        done[county] = rec
        OUT.write_text(json.dumps(done, indent=1))
        best = [d for d in rec["docs"] if d.get("has_senate")]
        print(f"[{n}/{len(args.counties)}] {county}: pages={len(rec['pages'])} nov_links={len(rec['nov_links'])} "
              f"live={len(rec['live_links'])} docs_with_senate={len(best)} "
              + (f"methods={best[0]['method_words_near_senate']}" if best else ""), file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
