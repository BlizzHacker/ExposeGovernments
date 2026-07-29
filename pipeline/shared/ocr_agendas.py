#!/usr/bin/env python3
"""
OCR the agenda PDFs that have no text layer.

    python3 shared/ocr_agendas.py sanangelo

Roughly two thirds of San Angelo's agendas are scans — the document is archived and
downloadable, but search cannot see inside it and the page has nothing to show. This
renders each page to an image, runs tesseract over it, and writes the recovered text
back into the meeting page.

OCR output is *labelled as OCR* wherever it appears. It is good enough to make an
agenda findable and readable; it is not good enough to quote verbatim without checking
the PDF, and the page says so.

Requires: tesseract-ocr, pymupdf.
"""

import argparse
import html as htmlmod
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("pip install pymupdf")

ROOT = Path(__file__).resolve().parent.parent
MIN_TEXT = 200          # below this a PDF is treated as having no usable text layer
DPI = 300               # tesseract does badly below ~250 on small agenda type


def have_tesseract():
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def ocr_pdf(path: Path) -> str:
    """Render each page and OCR it. Returns recovered text."""
    doc = fitz.open(path)
    out = []
    with tempfile.TemporaryDirectory() as td:
        for i, page in enumerate(doc):
            img = Path(td) / f"p{i}.png"
            page.get_pixmap(dpi=DPI).save(img)
            r = subprocess.run(
                ["tesseract", str(img), "stdout", "-l", "eng", "--psm", "6"],
                capture_output=True, text=True)
            if r.returncode == 0:
                out.append(r.stdout.strip())
    doc.close()
    text = "\n\n".join(t for t in out if t)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="re-OCR even if already done")
    a = ap.parse_args()

    if not have_tesseract():
        sys.exit("tesseract not installed:  apt-get install tesseract-ocr tesseract-ocr-eng")

    cfg = json.loads((ROOT / "chapters" / f"{a.chapter}.json").read_text(encoding="utf-8"))
    src = Path(cfg.get("source_dir") or (ROOT.parent / f"expose{a.chapter}"))
    src = src if src.is_absolute() else (ROOT / src).resolve()
    pages_dir = src / "src" / "pages"
    files_dir = src / "site" / "meetings" / "files"
    meta_path = src / "site" / "data" / "meetings.json"

    if not meta_path.exists():
        sys.exit(f"no meetings.json at {meta_path} — run ingest_agendas.py first")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    targets = [m for m in meta["meetings"] if m["chars"] < MIN_TEXT]
    if a.limit:
        targets = targets[:a.limit]
    print(f"  {len(targets)} agendas with no text layer")

    done = failed = 0
    for m in targets:
        pdf = files_dir / f"{m['slug']}-agenda.pdf"
        frag = pages_dir / f"70-meeting-{m['slug']}.html"
        if not pdf.exists() or not frag.exists():
            continue
        html = frag.read_text(encoding="utf-8")
        if "OCR-RECOVERED" in html and not a.force:
            continue

        text = ocr_pdf(pdf)
        if len(text) < 80:
            print(f"    {m['slug']}: OCR recovered nothing usable")
            failed += 1
            continue

        note = ("(Text below was recovered by OCR from a scanned PDF, so it may contain "
                "errors. The PDF above is the authority.)\n\n")
        block = htmlmod.escape(note + text, quote=True)[:120000]

        # Replace the placeholder body with the recovered text, and mark the page
        # so a later run skips it and a reader knows what they are looking at.
        html = re.sub(
            r"(<pre[^>]*>)(.*?)(</pre>)",
            lambda mm: mm.group(1) + block + mm.group(3),
            html, count=1, flags=re.S)
        html = html.replace("<!--meta", "<!--meta\nocr: OCR-RECOVERED", 1)
        frag.write_text(html, encoding="utf-8")

        m["chars"] = len(text)
        m["ocr"] = True
        done += 1
        print(f"    {m['slug']}: recovered {len(text):,} chars")

    meta_path.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"  OCR complete: {done} recovered, {failed} unusable")


if __name__ == "__main__":
    main()
