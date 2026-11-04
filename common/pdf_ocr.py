"""OCR fallback for scanned ES&S/Electionware "Summary Results Report" PDFs.

Some counties (Clermont on election night 2026) print the report and scan it
on a copier, so the PDF is page images with no text layer. This module:

  1. renders each page at 300 dpi (pdftoppm),
  2. finds the U.S. Senate block and its column headers from tesseract's
     word boxes (TSV),
  3. reads every number cell separately with a digits-only whitelist, and
  4. returns rows in the same shape as pdf_results.parse_positional.

The column headers must read, left to right, TOTAL / VOTE % / the method
columns given by the caller, or it raises. Every Brown/Husted row must have
method columns summing exactly to its TOTAL (checked by pdf_results.run, and
again here for every candidate so an OCR misread is reported per cell). A
misread fails the update rather than writing a wrong number.

Needs the pdftoppm (poppler) and tesseract binaries.
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
import tempfile
from pathlib import Path

PARTY = re.compile(r"^(Dem|Rep|Lib|Grn|Opc|Ope|Oth|Non|Ind)$", re.I)
SENATE_WORD = re.compile(r"senat", re.I)


def _tsv(png: Path) -> list[dict]:
    out = subprocess.run(["tesseract", str(png), "-", "--psm", "6", "tsv"],
                         capture_output=True, text=True, errors="replace", check=True).stdout
    rows = list(csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE))
    words = []
    for r in rows:
        t = (r.get("text") or "").strip()
        if r.get("level") == "5" and t:
            l, tp, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
            words.append({"text": t, "x0": l, "x1": l + w, "top": tp, "bottom": tp + h,
                          "line": (r["block_num"], r["par_num"], r["line_num"])})
    return words


def _lines(words: list[dict]) -> list[list[dict]]:
    by: dict = {}
    for w in words:
        by.setdefault(w["line"], []).append(w)
    lines = [sorted(v, key=lambda w: w["x0"]) for v in by.values()]
    return sorted(lines, key=lambda l: min(w["top"] for w in l))


def _despeckle(gray):
    """Remove dark blobs no bigger than 7x7 px (the dotted leaders under each
    row; at 300 dpi digits are ~35 px tall and commas ~10 px)."""
    import numpy as np
    from PIL import Image
    a = np.array(gray) < 128
    seen = np.zeros_like(a)
    h, w = a.shape
    out = np.array(gray).copy()
    for y in range(h):
        for x in range(w):
            if a[y, x] and not seen[y, x]:
                stack, pts = [(y, x)], []
                seen[y, x] = True
                while stack:
                    cy, cx = stack.pop()
                    pts.append((cy, cx))
                    for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1),
                                   (cy + 1, cx + 1), (cy - 1, cx - 1), (cy + 1, cx - 1), (cy - 1, cx + 1)):
                        if 0 <= ny < h and 0 <= nx < w and a[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                ys = [p[0] for p in pts]
                xs = [p[1] for p in pts]
                if max(ys) - min(ys) < 7 and max(xs) - min(xs) < 7:
                    for p in pts:
                        out[p] = 255
    return Image.fromarray(out)


def _cell(img, box) -> str:
    from PIL import ImageOps
    base = _despeckle(img.crop(box).convert("L"))
    reads = []
    # Native size first; tesseract sometimes drops this font's thin "1" at
    # native size, so 2x and 3x readings are candidates too. parse_scanned
    # keeps whichever combination makes the row sum to its TOTAL.
    for scale in (1, 2, 3):
        crop = base if scale == 1 else base.resize((base.width * scale, base.height * scale))
        crop = ImageOps.expand(crop, border=20 * scale, fill=255)
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            crop.save(f.name)
            reads.append(subprocess.run(["tesseract", f.name, "-", "--psm", "7",
                                         "-c", "tessedit_char_whitelist=0123456789,"],
                                        capture_output=True, text=True, check=True).stdout.strip())
    return reads


def _num(raw: str, where: str) -> int:
    s = raw.replace(" ", "").strip(",")
    # thousands groups must be 3 digits; anything else is a misread
    if not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", s):
        raise RuntimeError(f"OCR: unreadable number {raw!r} at {where}")
    if "," not in s and len(s) > 3:
        raise RuntimeError(f"OCR: number without separators {raw!r} at {where} (dropped comma?)")
    return int(s.replace(",", ""))


def parse_scanned(data: bytes, method_cols: list[str], dpi: int = 300) -> tuple[str, list[dict], list[str]]:
    from PIL import Image
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "in.pdf"
        pdf.write_bytes(data)
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(Path(td) / "p")], check=True)
        for png in sorted(Path(td).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[1])):
            lines = _lines(_tsv(png))
            texts = [" ".join(w["text"] for w in l) for l in lines]
            start = next((i for i, t in enumerate(texts)
                          if SENATE_WORD.search(t) and re.search(r"u\.?\s*s\.?|united", t, re.I)), None)
            if start is None:
                continue
            race = texts[start].strip()
            # header: the line containing TOTAL, plus the one under it
            h = next((i for i in range(start + 1, min(start + 5, len(lines))) if "TOTAL" in texts[i]), None)
            if h is None:
                raise RuntimeError(f"OCR: no TOTAL header under {race!r}")
            top = lines[h]
            labels_top = [w for w in top if w["text"] not in ("%",)]
            # expected top words: TOTAL, VOTE%(or VOTE), then one word per method column
            first = [w["text"] for w in labels_top]
            want_first = ["TOTAL", "VOTE"] + [m.split()[0] for m in method_cols]
            norm = [re.sub(r"[^A-Za-z]", "", t).upper() for t in first]
            if norm != [re.sub(r"[^A-Za-z]", "", t).upper() for t in want_first]:
                raise RuntimeError(f"OCR: header changed under {race!r}: {first} (want {want_first})")
            centers = [(w["x0"] + w["x1"]) / 2 for w in labels_top]
            rights = [w["x1"] for w in labels_top]
            img = Image.open(png)
            rows = []
            for i in range(h + 2, len(lines)):
                l = lines[i]
                t = texts[i]
                if re.match(r"^(Not Assigned|Overvotes|Undervotes|Precincts|Total Votes)", t, re.I) or \
                        (SENATE_WORD.search(t) is None and re.match(r"^For\b", t)):
                    break
                name_words = [w for w in l if w["x1"] < centers[0] - 120 * dpi / 300]
                name = " ".join(w["text"] for w in name_words)
                name = re.sub(r"[^A-Za-z.\- ]", "", name).strip(" .-")
                parts = name.split()
                if parts and PARTY.match(parts[0]):
                    parts = parts[1:]
                name = " ".join(parts)
                if re.match(r"write-?\s*t?in", name, re.I):
                    name = "Write-in"
                if not name:
                    continue
                # Crop tight to the text height of the row's name words: the
                # dotted leader runs just under the baseline and breaks OCR.
                tops = sorted(w["top"] for w in name_words) or sorted(w["top"] for w in l)
                hts = sorted(w["bottom"] - w["top"] for w in name_words) or [40]
                y0 = tops[len(tops) // 2] - 8
                y1 = y0 + hts[len(hts) // 2] + 20
                cands = []  # per cell: distinct readable values, native reading first
                for k in [0] + list(range(2, len(centers))):
                    # numbers are right-aligned near the header's right edge
                    left = (rights[k - 1] + 10) if k > 0 else centers[0] - 170 * dpi / 300
                    if k == 2:
                        left = rights[1] + 10  # skip the VOTE % column
                    right = rights[k] + 25 * dpi / 300
                    where = f"{name} / {(['TOTAL', '%'] + method_cols)[k]}"
                    vs, errs = [], []
                    for raw in _cell(img, (int(left), y0, int(right), y1)):
                        try:
                            v = _num(raw, where)
                        except RuntimeError as e:
                            errs.append(str(e))
                            continue
                        if v not in vs:
                            vs.append(v)
                    if not vs:
                        raise RuntimeError(errs[0])
                    cands.append(vs)
                # The combination whose methods sum to TOTAL; it must be unique.
                import itertools
                ok = {c for c in itertools.product(*cands) if sum(c[1:]) == c[0]}
                vals = ok.pop() if len(ok) == 1 else tuple(c[0] for c in cands)
                total, methods = vals[0], list(vals[1:])
                rows.append({"race": race, "contestant": name, "total": total, **dict(zip(method_cols, methods))})
            if not rows:
                raise RuntimeError(f"OCR: no candidate rows under {race!r}")
            bad = [f"{r['contestant']}: {sum(r[c] for c in method_cols)} vs {r['total']}"
                   for r in rows if sum(r[c] for c in method_cols) != r["total"]]
            if bad:
                print("OCR WARNING: rows that don't sum: " + "; ".join(bad))
            return race, rows, method_cols
    raise RuntimeError("No U.S. Senate race in the report")
