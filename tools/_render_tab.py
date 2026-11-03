"""Render one tab of the owner's sheet to PNG (via Google's PDF export), to check charts.

Usage: GSHEET_ID=<id> python -m tools._render_tab <tab> <out.png>
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image

from tools.push_sheet import session
from tools.sheet_validations import KEY

tab, out = sys.argv[1:3]
sid = os.environ["GSHEET_ID"]
s, _ = session(KEY)
api = f"https://sheets.googleapis.com/v4/spreadsheets/{sid}"
gid = next(x["properties"]["sheetId"] for x in s.get(api, params={"fields": "sheets.properties"}).json()["sheets"]
           if x["properties"]["title"] == tab)
r = s.get(f"https://docs.google.com/spreadsheets/d/{sid}/export",
          params={"format": "pdf", "gid": gid, "portrait": "false", "fitw": "true", "gridlines": "false"})
r.raise_for_status()
with tempfile.TemporaryDirectory() as d:
    pdf = os.path.join(d, "t.pdf")
    open(pdf, "wb").write(r.content)
    subprocess.run(["pdftoppm", "-r", os.environ.get("RENDER_DPI", "150"), "-f", "1", "-l", "1", "-png", pdf, os.path.join(d, "p")], check=True)
    png = next(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".png"))
    im = Image.open(png)
    w, h = im.size
    im.crop((int(w * 0.06), int(h * 0.08), int(w * 0.56), int(h * 0.46))).save(out)
print(out)
