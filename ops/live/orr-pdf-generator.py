#!/usr/bin/env python3
"""
Miami OK official Open Records Request PDF generator.

Builds a print-ready packet:
1. The official City of Miami Request for Records/Copies form.
2. A concise "see attached" request line on the form.
3. Full request text on typed attachment pages.

Deploy to: LXC 170 /opt/orr-pdf-generator.py
Deps: pymupdf
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz


MWF_NAME = "Move Weight Foundation"
MWF_PHONE = "310-658-6281"
MWF_ADDRESS = os.environ.get("ORR_REQUESTER_ADDRESS", "")
MWF_CITY_STATE_ZIP = os.environ.get("ORR_REQUESTER_CITY_STATE_ZIP", "")
MWF_SIGNATURE = "Move Weight Foundation"

OUTPUT_DIR = Path(os.environ.get("ORR_OUTPUT_DIR", "/var/www/exposemiamiok/html/foia/generated"))
TEMPLATE_PATH = Path(os.environ.get("ORR_TEMPLATE_PATH", "/opt/miami-orr-form-template.pdf"))

TITLE_BY_ID = {
    "cae20260803a1": "City Attorney / July 28 Email Records",
}


def normalize_text(value: str) -> str:
    value = value or ""
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\xa0": " ",
        "\u00a7": "Section",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()).strip()


def ensure_template() -> Path:
    if not TEMPLATE_PATH.exists():
        import subprocess

        TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "curl",
                "-sL",
                "-o",
                str(TEMPLATE_PATH),
                "https://www.miamiok.gov/DocumentCenter/View/886/OPEN-RECORDS-REQUEST-FORM",
            ],
            check=True,
        )
    return TEMPLATE_PATH


def parse_iso(value: str) -> str:
    if not value:
        return "Not listed"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    dt = dt.astimezone(timezone.utc)
    return f"{dt.strftime('%B')} {dt.day}, {dt.year} at {dt.strftime('%H:%M')} UTC"


def infer_title(foia_data: dict) -> str:
    explicit = normalize_text(foia_data.get("title", ""))
    if explicit:
        return explicit
    request_id = str(foia_data.get("id", ""))
    if request_id in TITLE_BY_ID:
        return TITLE_BY_ID[request_id]
    description = normalize_text(foia_data.get("description", ""))
    first_line = next((line for line in description.splitlines() if line), "")
    first_line = re.sub(r"^Pursuant to .*?requests?\s*", "", first_line, flags=re.IGNORECASE)
    return (first_line[:72].rstrip(" ,.;:-") or "Open Records Request")


def text_width(text: str, fontname: str, fontsize: float) -> float:
    return fitz.get_text_length(text, fontname=fontname, fontsize=fontsize)


def wrap_words(text: str, max_width: float, fontname: str, fontsize: float) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if text_width(candidate, fontname, fontsize) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
        if text_width(word, fontname, fontsize) <= max_width:
            current = word
            continue

        chunk = ""
        for char in word:
            test = f"{chunk}{char}"
            if text_width(test, fontname, fontsize) <= max_width:
                chunk = test
            else:
                if chunk:
                    lines.append(chunk)
                chunk = char
        current = chunk

    if current:
        lines.append(current)
    return lines


class AttachmentWriter:
    def __init__(self, doc: fitz.Document, title: str, request_id: str):
        self.doc = doc
        self.title = title
        self.request_id = request_id
        self.page_no = 1
        self.page: fitz.Page | None = None
        self.y = 82.0
        self.bottom = 742.0
        self.new_page()

    def new_page(self) -> None:
        self.page = self.doc.new_page(width=612, height=792)
        page = self.page
        page.insert_text((54, 48), "Detailed Open Records Request Attachment", fontsize=13, fontname="hebo")
        page.insert_text((437, 48), f"Tracking ID: {self.request_id}", fontsize=8.5, fontname="helv", color=(0.32, 0.32, 0.32))
        page.draw_line((54, 62), (558, 62), color=(0.72, 0.72, 0.72), width=0.8)
        page.insert_text((258, 770), f"Attachment page {self.page_no}", fontsize=8, fontname="helv", color=(0.42, 0.42, 0.42))
        self.page_no += 1
        self.y = 82.0

    def ensure_space(self, points: float) -> None:
        if self.y + points > self.bottom:
            self.new_page()

    def line(self, text: str, x: float = 54, fontsize: float = 10, fontname: str = "helv", leading: float = 14) -> None:
        self.ensure_space(leading)
        assert self.page is not None
        self.page.insert_text((x, self.y), text, fontsize=fontsize, fontname=fontname)
        self.y += leading

    def blank(self, points: float = 8) -> None:
        self.ensure_space(points)
        self.y += points

    def heading(self, text: str) -> None:
        self.blank(6)
        self.line(text, fontsize=10.5, fontname="hebo", leading=16)

    def field(self, label: str, value: str) -> None:
        label_text = f"{label}:"
        label_width = text_width(label_text, "hebo", 9.5) + 7
        x = 54
        value_x = x + label_width
        max_width = 558 - value_x
        lines = wrap_words(normalize_text(value), max_width, "helv", 9.5)

        self.ensure_space(max(1, len(lines)) * 13)
        assert self.page is not None
        self.page.insert_text((x, self.y), label_text, fontsize=9.5, fontname="hebo")
        for index, line in enumerate(lines):
            self.page.insert_text((value_x, self.y + index * 13), line, fontsize=9.5, fontname="helv")
        self.y += max(1, len(lines)) * 13 + 3

    def paragraph(self, text: str, x: float = 54, max_width: float = 504, fontsize: float = 10, leading: float = 14) -> None:
        text = normalize_text(text)
        if not text:
            self.blank(6)
            return
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                self.blank(6)
                continue
            indent = 0
            if re.match(r"^[a-z]\.", line, flags=re.IGNORECASE):
                indent = 18
            elif line.startswith(("-", "*")):
                indent = 18

            for wrapped in wrap_words(line, max_width - indent, "helv", fontsize):
                self.line(wrapped, x=x + indent, fontsize=fontsize, fontname="helv", leading=leading)
            self.blank(4)


def draw_form_page_one(page: fitz.Page, foia_data: dict) -> None:
    request_id = str(foia_data.get("id", "unknown"))
    title = infer_title(foia_data)

    page.insert_text((101, 196), MWF_NAME, fontsize=10, fontname="helv")
    page.insert_text((379, 196), MWF_PHONE, fontsize=10, fontname="helv")
    if MWF_ADDRESS:
        page.insert_text((134, 223), MWF_ADDRESS, fontsize=10, fontname="helv")
    if MWF_CITY_STATE_ZIP:
        page.insert_text((395, 223), MWF_CITY_STATE_ZIP, fontsize=10, fontname="helv")
    page.insert_text((114, 251), MWF_SIGNATURE, fontsize=10, fontname="helv")

    page.insert_text((58, 622), f"See attached detailed request. Tracking ID: {request_id}", fontsize=9, fontname="helv")
    page.insert_text((420, 622), "1 set", fontsize=9, fontname="helv")
    page.insert_text((58, 650), title[:72], fontsize=9, fontname="helv")
    page.insert_text((420, 650), "Electronic preferred", fontsize=9, fontname="helv")


def draw_form_page_two(page: fitz.Page) -> None:
    page.insert_text((379, 46), "X", fontsize=13, fontname="hebo")


def add_attachment(doc: fitz.Document, foia_data: dict) -> None:
    request_id = str(foia_data.get("id", "unknown"))
    title = infer_title(foia_data)
    writer = AttachmentWriter(doc, title, request_id)

    recipient = normalize_text(foia_data.get("recipient_name", "")) or normalize_text(foia_data.get("agency", ""))
    recipient_email = normalize_text(foia_data.get("recipient_email", ""))
    details = normalize_text(foia_data.get("details", ""))
    description = normalize_text(foia_data.get("description", ""))

    writer.field("Request", title)
    writer.field("Recipient", recipient or "City Clerk - City of Miami, OK")
    if recipient_email:
        writer.field("Recipient Email", recipient_email)
    requester_parts = [MWF_NAME]
    if MWF_ADDRESS:
        requester_parts.append(MWF_ADDRESS)
    if MWF_CITY_STATE_ZIP:
        requester_parts.append(MWF_CITY_STATE_ZIP)
    writer.field("Requester", ", ".join(requester_parts))
    writer.field("Phone", MWF_PHONE)
    writer.field("Submitted in Platform", parse_iso(foia_data.get("created_at", "")))
    writer.field("Commercial Purpose", "No. This is a non-commercial public-interest transparency request.")
    writer.field("Preferred Format", "Electronic records by email where available; otherwise one complete set of printed copies.")

    writer.heading("Records Requested")
    writer.paragraph(description)

    if details:
        writer.heading("Additional Details")
        writer.paragraph(details)

    writer.heading("Fee and Fulfillment Request")
    writer.paragraph(
        "Please provide an itemized estimate before incurring fees. The Move Weight Foundation is prepared to pay "
        "reasonable fees authorized by the Oklahoma Open Records Act. If any portion of the request is denied or "
        "withheld, please identify the specific legal basis for withholding and release all reasonably segregable "
        "public records."
    )

    writer.blank(12)
    writer.line("Respectfully submitted,", fontsize=10, leading=18)
    writer.line(MWF_SIGNATURE, fontsize=10, fontname="hebo", leading=14)


def generate_orr_pdf(foia_data: dict, output_filename: str | None = None) -> Path:
    template = ensure_template()
    doc = fitz.open(str(template))

    if doc.page_count < 2:
        raise RuntimeError("Official ORR template must contain at least two pages")

    draw_form_page_one(doc[0], foia_data)
    draw_form_page_two(doc[1])
    add_attachment(doc, foia_data)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not output_filename:
        request_id = str(foia_data.get("id", "unknown"))
        output_filename = f"orr-{request_id[:12]}.pdf"

    output_path = OUTPUT_DIR / output_filename
    if output_path.exists():
        output_path.unlink()
    doc.save(str(output_path), garbage=4, deflate=True)
    doc.close()
    return output_path


def load_request_from_file(path: Path, request_id: str | None = None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("requests", data) if isinstance(data, dict) else data
    if isinstance(records, dict):
        return records
    if request_id:
        for record in records:
            if str(record.get("id")) == request_id:
                return record
        raise KeyError(f"Request ID not found: {request_id}")
    if len(records) != 1:
        raise ValueError("Provide a request ID when the JSON file contains multiple requests")
    return records[0]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a printable Miami OK open-records request packet.")
    parser.add_argument("json_file", nargs="?", help="JSON file containing one request or a requests list.")
    parser.add_argument("request_id", nargs="?", help="Request ID to generate from a requests list.")
    parser.add_argument("--output", help="Output filename.")
    args = parser.parse_args()

    if args.json_file:
        record = load_request_from_file(Path(args.json_file), args.request_id)
    else:
        record = {
            "id": "test-12345",
            "title": "Test Open Records Request",
            "description": "All city council meeting minutes from January 2026 to present.",
            "recipient_name": "City Clerk - City of Miami, OK",
            "recipient_email": "cityclerk@miamiok.gov",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    print(generate_orr_pdf(record, args.output))
