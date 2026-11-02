"""Push county_results.csv into ONE tab of the owner's own Google Sheet.

Replaces that tab's contents with the CSV (the rest of the spreadsheet is
never touched; the tab is created if it doesn't exist). Runs as a Google
Cloud service account the owner creates and shares the sheet with.

Safety:
  - refuses the AP aggregator's production spreadsheet ID (PROD_IDS)
  - writes only the named tab (default "methods"); never deletes tabs
  - the key file lives outside the repo (default
    ~/.config/scrapers2026/google-sa.json) and must not be readable by
    other users of the Mac

Config (environment variables):
  GSHEET_ID     the spreadsheet ID, from its URL: docs.google.com/spreadsheets/d/<ID>/edit
  GSHEET_TAB    tab name (default "methods")
  GSHEET_KEY    service-account key path (default ~/.config/scrapers2026/google-sa.json)

Usage:
    GSHEET_ID=... python -m tools.push_sheet [path/to/county_results.csv]
    GSHEET_ID=... python -m tools.push_sheet --check    # auth + access test, writes nothing
"""

from __future__ import annotations

import csv
import os
import stat
import sys
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT.parent / "exports" / "county_results.csv"
DEFAULT_KEY = Path.home() / ".config" / "scrapers2026" / "google-sa.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
API = "https://sheets.googleapis.com/v4/spreadsheets"
# Never write here: the colleagues' AP county aggregator (production).
PROD_IDS = {"1XSAUBbz4ykfZKz47386hAovYS_Pq3tsLdrEASPXvT7M"}
# Columns kept as text (FIPS has to stay '39001', not a number).
TEXT_COLS = {"state_code", "county_fips", "reporting_unit_name", "reporting_status",
             "latest_data_as_of", "refreshed_sheet_as_of", "method_source",
             "has_mail_inperson_split", "notes"}


def session(key: Path):
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    if not key.exists():
        raise SystemExit(f"No service-account key at {key} (see README: Google Sheet updates)")
    mode = key.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SystemExit(f"{key} is readable by other users; run: chmod 600 {key}")
    creds = service_account.Credentials.from_service_account_file(str(key), scopes=SCOPES)
    return AuthorizedSession(creds), creds.service_account_email


def typed(rows: list[list[str]]) -> list[list]:
    """Numbers as numbers (so the sheet can sum them), the rest as text."""
    header, out = rows[0], [rows[0]]
    for r in rows[1:]:
        cells = []
        for name, v in zip(header, r):
            if name in TEXT_COLS or v == "":
                cells.append(v)
                continue
            try:
                f = float(v)
                cells.append(int(f) if f.is_integer() and "." not in v else f)
            except ValueError:
                cells.append(v)
        out.append(cells)
    return out


def tab_id(s, sheet_id: str, tab: str) -> int | None:
    r = s.get(f"{API}/{sheet_id}", params={"fields": "properties.title,sheets.properties"}, timeout=30)
    if r.status_code in (403, 404):
        raise SystemExit(f"Can't open spreadsheet {sheet_id} (HTTP {r.status_code}). Share it with the "
                         "service account's email as Editor, and check the ID.")
    r.raise_for_status()
    for sh in r.json().get("sheets", []):
        if sh["properties"]["title"] == tab:
            return sh["properties"]["sheetId"]
    return None


def push(csv_path: Path, sheet_id: str, tab: str, key: Path, check_only: bool = False) -> int:
    if sheet_id in PROD_IDS:
        raise SystemExit("Refusing: that's the AP aggregator's production sheet. Use your own sheet's ID.")
    s, email = session(key)
    existing = tab_id(s, sheet_id, tab)
    if check_only:
        print(f"OK: {email} can open {sheet_id}; tab {tab!r} "
              + ("exists" if existing is not None else "will be created on first push"), file=sys.stderr)
        return 0
    rows = list(csv.reader(csv_path.open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        raise SystemExit(f"{csv_path} has no data rows; not pushing")
    if existing is None:
        r = s.post(f"{API}/{sheet_id}:batchUpdate", timeout=30,
                   json={"requests": [{"addSheet": {"properties": {"title": tab}}}]})
        r.raise_for_status()
    rng = quote(f"'{tab}'", safe="")
    # Clear first so a shorter push can't leave stale rows or columns behind.
    s.post(f"{API}/{sheet_id}/values/{rng}:clear", timeout=30).raise_for_status()
    r = s.put(f"{API}/{sheet_id}/values/{rng}!A1", params={"valueInputOption": "RAW"},
              json={"values": typed(rows)}, timeout=60)
    r.raise_for_status()
    print(f"Google Sheet: {len(rows) - 1} rows -> tab {tab!r} of {sheet_id}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    sheet_id = os.environ.get("GSHEET_ID", "").strip()
    if not sheet_id:
        print("GSHEET_ID not set; nothing to do (see README: Google Sheet updates)", file=sys.stderr)
        return 2
    tab = os.environ.get("GSHEET_TAB", "methods")
    key = Path(os.environ.get("GSHEET_KEY", DEFAULT_KEY)).expanduser()
    check = "--check" in args
    files = [a for a in args if a != "--check"]
    try:
        return push(Path(files[0]) if files else DEFAULT_CSV, sheet_id, tab, key, check)
    except requests.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else ""
        print(f"ERROR Google Sheets API: {e} {body}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
