#!/usr/bin/env python3
"""Cover images for the per-area GoFundMe campaigns.

    python3 shared/make_campaign_covers.py

Writes generated/campaign-covers/<key>.png at 1200x675.

Why generated rather than photographed: a donor scrolling GoFundMe sees the card
before they see a word of the story, and fourteen campaigns that look like one
organisation read as an organisation. A photograph of a city hall would say
nothing about what this is. The card says what the chapter already holds, in
numbers the donor can go and check, which is the same argument the story makes.

The counts come from each chapter's own published data, not from a spreadsheet
typed by hand - if a number on the card is wrong, the chapter is wrong too and
both get fixed together.
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / "chapters"
OUT = ROOT / "generated" / "campaign-covers"

W, H = 1200, 675
BG = (12, 15, 20)
PANEL = (19, 24, 34)
INK = (238, 242, 248)
DIM = (150, 163, 184)
ACCENT = (232, 89, 12)
RULE = (44, 53, 71)

# Candidate faces per role, first hit wins. These were Windows-only paths, and
# ImageFont.truetype() raises OSError on a missing file - which font() caught,
# falling back to PIL's built-in bitmap face. That face ignores the requested
# size, so running this on the node produced fourteen cards with 11px type
# scattered across a 1200x675 canvas and no error anywhere. The covers looked
# like a broken template rather than a fundraiser.
BOLD = ["C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
REG = ["C:/Windows/Fonts/arial.ttf",
       "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
       "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
NARROW = ["C:/Windows/Fonts/ARIALNB.TTF"] + BOLD

F, FR, FN = BOLD, REG, NARROW


def font(paths, size):
    """First installed face from the candidate list, at the size asked for.

    Refuses to silently fall back to the built-in bitmap font: a cover is a
    public fundraising asset, and one rendered at the wrong size is worse than
    a build that stops and says which font is missing.
    """
    for p in ([paths] if isinstance(paths, str) else paths):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    raise SystemExit(
        "no usable TrueType font found - tried: "
        + ", ".join([paths] if isinstance(paths, str) else paths))


def wid(d, text, f):
    return d.textbbox((0, 0), text, font=f)[2]


def _tally(ms):
    ag = sum(1 for x in ms if x.get("agenda") or x.get("agenda_url")
             or int(x.get("chars") or 0) > 200)
    vi = sum(1 for x in ms if x.get("video") or x.get("video_url") or x.get("video_id"))
    return len(ms), ag, vi


def _live(cfg):
    """Read the chapter's own published data.

    The three founding chapters are built by the refresh pipeline from a tree
    this one does not hold, so locally they look empty. Putting a zero on San
    Angelo's card - a chapter with 48 indexed meetings and 47 of them searchable
    - would be the single most misleading thing on the image.
    """
    import urllib.request
    host = cfg.get("canonical_host") or cfg["domain"]
    try:
        req = urllib.request.Request(f"https://{host}/data/meetings.json",
                                     headers={"User-Agent": "MoveWeight/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return 0, 0, 0
    ms = d["meetings"] if isinstance(d, dict) and "meetings" in d else d
    return _tally(ms) if isinstance(ms, list) else (0, 0, 0)


OVERRIDE = ROOT / "generated" / "cover-counts-override.json"


def counts(cfg):
    """Meetings / agendas / video for this chapter, from its own data."""
    # San Angelo serves `location /data/ { return 404; }` and is built from a
    # tree this one does not hold, so neither path below can see it. The
    # override carries figures read off its container, with the date they were
    # read - better than silently printing a zero on the card.
    if OVERRIDE.exists():
        try:
            o = json.loads(OVERRIDE.read_text(encoding="utf-8")).get(cfg["key"])
            if o:
                return o["meetings"], o["agendas"], o["video"]
        except (OSError, ValueError, KeyError):
            pass
    src = (ROOT / cfg.get("source_dir", "")).resolve()
    m = src / "generated" / "meetings.json"
    if not m.exists():
        m = src / "site" / "data" / "meetings.json"
    if not m.exists():
        return _live(cfg)
    try:
        d = json.loads(m.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _live(cfg)
    ms = d["meetings"] if isinstance(d, dict) and "meetings" in d else d
    if not isinstance(ms, list) or not ms:
        return _live(cfg)
    ag = sum(1 for x in ms if x.get("agenda") or x.get("agenda_url")
             or int(x.get("chars") or 0) > 200)
    vi = sum(1 for x in ms if x.get("video") or x.get("video_url") or x.get("video_id"))
    return len(ms), ag, vi


def cover(cfg, path):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # A single warm bar down the left edge. One accent, used once.
    d.rectangle([0, 0, 14, H], fill=ACCENT)

    f_eyebrow = font(F, 26)
    f_head = font(F, 92)
    f_city = font(F, 54)
    f_num = font(FN, 68)
    f_lab = font(FR, 22)
    f_url = font(F, 30)

    x = 78
    d.text((x, 74), "MOVE WEIGHT FOUNDATION", font=f_eyebrow, fill=DIM)

    # "Funding the Truth" with the one word that carries the accent.
    y = 138
    a = "Funding the "
    d.text((x, y), a, font=f_head, fill=INK)
    d.text((x + wid(d, a, f_head), y), "Truth", font=f_head, fill=ACCENT)

    city = f"in {cfg['city']}, {cfg['state_abbr']}"
    d.text((x, y + 108), city, font=f_city, fill=INK)

    d.line([(x, 372), (W - 78, 372)], fill=RULE, width=2)

    n, ag, vi = counts(cfg)
    stats = [(f"{n:,}", "public meetings indexed")]
    if ag:
        # "with agenda text" was false wherever the count comes from an agenda
        # URL rather than extracted text - Abilene has 229 agenda documents
        # attached and none of them OCR'd, and the card claimed otherwise.
        stats.append((f"{ag:,}", "with agendas attached"))
    if vi:
        stats.append((f"{vi:,}", "with video"))
    stats.append(("Weekly", "refreshed automatically"))

    sx = x
    for value, label in stats[:4]:
        d.text((sx, 410), value, font=f_num, fill=INK)
        d.text((sx, 492), label, font=f_lab, fill=DIM)
        sx += max(wid(d, value, f_num), wid(d, label, f_lab)) + 58

    host = cfg.get("canonical_host") or cfg["domain"]
    d.rectangle([x, 566, x + wid(d, host, f_url) + 36, 566 + 56], fill=PANEL)
    d.text((x + 18, 578), host, font=f_url, fill=ACCENT)

    tag = "Public records. Published whole."
    d.text((W - 78 - wid(d, tag, f_lab), 596), tag, font=f_lab, fill=DIM)

    img.save(path, "PNG", optimize=True)
    return n, ag, vi


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    keys = sys.argv[1:]
    made = 0
    for p in sorted(CHAPTERS.glob("*.json")):
        if p.stem.startswith("_") or (keys and p.stem not in keys):
            continue
        cfg = json.loads(p.read_text(encoding="utf-8"))
        out = OUT / f"{cfg['key']}.png"
        n, ag, vi = cover(cfg, out)
        print(f"  {cfg['key']:14s} {n:5d} meetings  {ag:5d} agenda  {vi:5d} video  -> {out.name}")
        made += 1
    print(f"\n  {made} covers -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
