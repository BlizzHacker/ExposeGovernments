#!/usr/bin/env python3
"""
Generate the Foundation's map assets from real boundary data.

    python3 shared/make_maps.py

Produces:
    shared/assets/us-expansion.svg     all 50 states, chapters highlighted
    shared/assets/state-<ab>.svg       a single state, cities marked

Everything is projected from an actual US states GeoJSON — no hand-drawn shapes.
A transparency project that ships a map with the wrong border has undermined its
own argument before anyone reads a word.

Projection is Albers equal-area conic, the standard for US national maps: it keeps
state areas honest, where a plain lat/long plot stretches the northern states badly.
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT.parent / "states.json"
OUT = ROOT / "shared" / "assets"
RESEARCH = ROOT / "research" / "cities.json"
CHAPTER_DIR = ROOT / "chapters"

STATE_NAME = {"OK": "Oklahoma", "TX": "Texas", "MS": "Mississippi"}


def load_chapters():
    """Every chapter, with its coordinates, read from the chapter configs.

    This used to be a hardcoded dict of three cities. It went stale the moment
    the fourth chapter launched, and a transparency project whose own map
    understates its coverage is making the same mistake it complains about.

    Coordinates come from research/cities.json, which records the Census
    Gazetteer internal point and GEOID for each place - see `coordinates._source`
    there. A city is drawn only if it has a real coordinate; nothing is
    approximated onto the map.
    """
    coords = json.loads(RESEARCH.read_text(encoding="utf-8")).get("coordinates", {})
    out = {}
    for p in sorted(CHAPTER_DIR.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        cfg = json.loads(p.read_text(encoding="utf-8"))
        c = coords.get(cfg["key"])
        if not c:
            print(f"  ! {cfg['key']}: no coordinate recorded, left off the map")
            continue
        state = STATE_NAME.get(cfg["state_abbr"], cfg.get("state"))
        entry = out.setdefault(state, {"status": "live", "cities": []})
        entry["cities"].append((cfg["city"], c["lon"], c["lat"],
                                cfg.get("canonical_host") or cfg["domain"]))
    for st in out.values():
        st["cities"].sort(key=lambda c: c[0])
    return out


CHAPTERS = load_chapters()

PALETTE = {
    "live":    "#e8590c",
    "next":    "#f0a020",
    "none":    "#1b2130",
    "stroke":  "#2c3547",
    "text":    "#eef2f8",
    "muted":   "#6f7d95",
}

W, H = 1000, 620


def albers(lon, lat, lon0=-96.0, lat0=37.5, p1=29.5, p2=45.5):
    """Albers equal-area conic.

    The textbook formula returns a NORTH-POSITIVE y, because it is written for
    ordinary maths axes. SVG's y axis grows downward. The original version
    returned the textbook value straight into SVG coordinates, so every map this
    file has ever produced was upside down - Alaska at the bottom of the canvas,
    Florida at the top. With three pins arranged in a rough triangle it was not
    obvious; with fourteen it is unmissable.

    The sign is flipped here, once, so every caller gets screen coordinates.
    """
    lon0r, lat0r = math.radians(lon0), math.radians(lat0)
    p1r, p2r = math.radians(p1), math.radians(p2)
    lon, lat = math.radians(lon), math.radians(lat)
    n = 0.5 * (math.sin(p1r) + math.sin(p2r))
    if abs(n) < 1e-9:
        n = 1e-9
    C = math.cos(p1r) ** 2 + 2 * n * math.sin(p1r)
    rho0 = math.sqrt(C - 2 * n * math.sin(lat0r)) / n
    rho = math.sqrt(max(C - 2 * n * math.sin(lat), 0)) / n
    theta = n * (lon - lon0r)
    return rho * math.sin(theta), rho * math.cos(theta) - rho0


# Alaska and Hawaii at their true positions dominate the bounding box: Alaska
# alone is wider than the lower 48 and sits far to the northwest, which squashes
# every state anyone actually reads down into a corner. Every US national map
# solves this the same way - project them separately, scale Alaska down, and
# inset both at the bottom left. Their own projections use their own standard
# parallels so neither is distorted by being drawn at Kansas's.
INSETS = {
    "Alaska": {"lon0": -152.0, "lat0": 60.0, "p1": 55.0, "p2": 65.0,
               "scale": 0.36, "at": (0.055, 0.80)},
    "Hawaii": {"lon0": -157.0, "lat0": 20.5, "p1": 8.0, "p2": 18.0,
               "scale": 0.30, "at": (0.20, 0.90)},
}


def rings(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return [c[0]]
    if t == "MultiPolygon":
        return [p[0] for p in c]
    return []


def _simplify(pxs):
    """Drop near-duplicate points.

    The source data is far denser than a 1000px canvas can show, and keeping it
    all makes an 89 KB file of noise.
    """
    out, last = [], None
    for px, py in pxs:
        if last and abs(px - last[0]) < 0.45 and abs(py - last[1]) < 0.45:
            continue
        out.append((px, py))
        last = (px, py)
    return out


def build(features, wanted=None, pad=24, insets=True):
    """Project, fit to the viewbox, and return per-state SVG paths.

    Returns (paths, to_px). `to_px` maps a lon/lat to canvas pixels using the
    main projection - the one the lower 48 is fitted to. Inset states get their
    own transform, so a pin inside one is placed by the same function that drew
    it rather than by the mainland fit.
    """
    use_insets = insets and not wanted
    inset_names = set(INSETS) if use_insets else set()

    pts, prepared, deferred = [], [], []
    for f in features:
        name = f["properties"]["name"]
        if wanted and name not in wanted:
            continue
        polys = [xy for xy in
                 ([albers(lon, lat) for lon, lat in ring] for ring in rings(f["geometry"]))
                 if len(xy) > 3]
        if not polys:
            continue
        if name in inset_names:
            deferred.append(name)
            continue
        prepared.append((name, polys))
        # Only the mainland contributes to the bounding box. This is the whole
        # point of the inset: Alaska must not decide the scale of Rhode Island.
        for ring in polys:
            pts.extend(ring)
    if not pts:
        return [], (lambda lon, lat: (0, 0))

    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    scale = min((W - 2 * pad) / (maxx - minx), (H - 2 * pad) / (maxy - miny))
    ox = (W - (maxx - minx) * scale) / 2 - minx * scale
    oy = (H - (maxy - miny) * scale) / 2 - miny * scale

    def to_px(lon, lat):
        x, y = albers(lon, lat)
        return x * scale + ox, y * scale + oy

    out = []
    for name, polys in prepared:
        d = ["M" + " ".join(f"{x:.1f},{y:.1f}" for x, y in r) + "Z"
             for r in (_simplify([(x * scale + ox, y * scale + oy) for x, y in ring])
                       for ring in polys) if len(r) > 3]
        if d:
            out.append((name, " ".join(d)))

    # Inset states, each on its own projection and its own local fit.
    placers = {}
    for name in deferred:
        cfg = INSETS[name]
        feat = next(f for f in features if f["properties"]["name"] == name)
        polys = [xy for xy in
                 ([albers(lon, lat, cfg["lon0"], cfg["lat0"], cfg["p1"], cfg["p2"])
                   for lon, lat in ring] for ring in rings(feat["geometry"]))
                 if len(xy) > 3]
        ipts = [p for ring in polys for p in ring]
        if not ipts:
            continue
        ixs, iys = [p[0] for p in ipts], [p[1] for p in ipts]
        iw, ih = max(ixs) - min(ixs), max(iys) - min(iys)
        # Sized as a fraction of the canvas so the inset stays proportionate if
        # the viewbox ever changes.
        target = W * 0.30 * cfg["scale"]
        isc = target / iw if iw else 1.0
        iox = W * cfg["at"][0] - min(ixs) * isc
        ioy = H * cfg["at"][1] - (min(iys) + ih / 2) * isc

        def _mk(isc=isc, iox=iox, ioy=ioy, cfg=cfg):
            def f(lon, lat):
                x, y = albers(lon, lat, cfg["lon0"], cfg["lat0"], cfg["p1"], cfg["p2"])
                return x * isc + iox, y * isc + ioy
            return f
        placers[name] = _mk()

        d = ["M" + " ".join(f"{x:.1f},{y:.1f}" for x, y in r) + "Z"
             for r in (_simplify([(x * isc + iox, y * isc + ioy) for x, y in ring])
                       for ring in polys) if len(r) > 3]
        if d:
            out.append((name, " ".join(d)))

    return out, to_px


def place_labels(pins, dy=13.0, char=6.4, line=13.0):
    """Place labels near their dots without letting them overlap each other.

    Texas alone carries seven chapters, and Dallas, Austin, San Antonio and
    Houston sit within a few dozen pixels of one another at national scale.

    The first version compared only vertical distance against a fixed 78px
    horizontal window, which is not what an overlap is: it pushed "Oklahoma City"
    hundreds of pixels from its dot while leaving genuinely clashing pairs alone.
    This one builds an actual bounding box per label from its text length and
    tests box intersection, trying candidate offsets nearest-first so a label
    only moves as far as it has to and always stays tied to its dot.
    """
    def box(x, y, w):
        return (x - w / 2 - 1, y - line * 0.78, x + w / 2 + 1, y + line * 0.28)

    def hits(b, placed):
        return any(not (b[2] < o[0] or b[0] > o[2] or b[3] < o[1] or b[1] > o[3])
                   for o in placed)

    # Candidate offsets from the dot, closest first: above, below, then further
    # out in whole line-heights.
    offsets = [-dy, dy + 3]
    for k in range(1, 4):
        offsets += [-dy - k * line, dy + 3 + k * line]

    placed, out = [], []
    # Densest areas first: a city with many neighbours should get the slot
    # nearest its dot, and the isolated ones can afford to move.
    order = sorted(pins, key=lambda p: (-sum(
        1 for q in pins if abs(q[1] - p[1]) < 90 and abs(q[2] - p[2]) < 40), p[2]))
    for city, x, y, host in order:
        w = len(city) * char
        chosen = None
        for off in offsets:
            b = box(x, y + off, w)
            if not hits(b, placed):
                chosen = y + off
                placed.append(b)
                break
        if chosen is None:
            chosen = y - dy
            placed.append(box(x, chosen, w))
        out.append((city, x, y, chosen, host))
    return out


def us_map(features):
    paths, to_px = build(features)
    body, markers = [], []
    for name, d in paths:
        ch = CHAPTERS.get(name)
        fill = PALETTE[ch["status"]] if ch else PALETTE["none"]
        cls = "st live" if ch else "st"
        n = len(ch["cities"]) if ch else 0
        label = f" — {n} chapter{'s' if n != 1 else ''} live" if ch else " — no chapter yet"
        body.append(f'<path class="{cls}" d="{d}" fill="{fill}" '
                    f'stroke="{PALETTE["stroke"]}" stroke-width="0.8">'
                    f'<title>{name}{label}</title></path>')

    pins = [(city, *to_px(lon, lat), host)
            for ch in CHAPTERS.values() for city, lon, lat, host in ch["cities"]]
    for city, x, y, ly, host in place_labels(pins):
        # A leader line only where the label had to move off the dot, so the
        # uncrowded pins stay clean.
        leader = ("" if abs(ly - (y - 13)) < 0.6 else
                  f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{ly + 4:.1f}" '
                  f'stroke="{PALETTE["muted"]}" stroke-width="0.7" opacity=".65"/>')
        markers.append(
            f'<a href="https://{host}/" target="_blank" class="pin">'
            f'<title>{city} — open the chapter</title>{leader}'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{PALETTE["live"]}" '
            f'opacity="0.22"><animate attributeName="r" values="8;15;8" dur="3s" '
            f'repeatCount="indefinite"/></circle>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="#fff"/>'
            f'<text x="{x:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="12.5" '
            f'font-weight="700" fill="{PALETTE["text"]}" '
            f'stroke="#0f172a" stroke-width="2.6" paint-order="stroke" '
            f'stroke-linejoin="round">{city}</text></a>')

    live = len(CHAPTERS)
    chapters = sum(len(c["cities"]) for c in CHAPTERS.values())
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img"
     aria-label="Map of the United States showing {chapters} Move Weight Foundation chapters across {", ".join(CHAPTERS)}">
  <style>
    .st {{ transition: fill .2s; }}
    .st.live:hover {{ fill: #ff922b; }}
    .pin {{ cursor: pointer; }}
    .pin:hover text {{ fill: #ff922b; }}
    text {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
  </style>
  <rect width="{W}" height="{H}" fill="none"/>
  {chr(10).join("  " + b for b in body)}
  {chr(10).join("  " + m for m in markers)}
  <g transform="translate(24,{H - 74})">
    <rect x="0" y="0" width="16" height="16" rx="3" fill="{PALETTE['live']}"/>
    <text x="24" y="13" font-size="14" fill="{PALETTE['text']}">{chapters} chapters live across {live} states</text>
    <rect x="0" y="26" width="16" height="16" rx="3" fill="{PALETTE['none']}" stroke="{PALETTE['stroke']}"/>
    <text x="24" y="39" font-size="14" fill="{PALETTE['muted']}">{50 - live} states still unwatched</text>
  </g>
</svg>
'''


def state_map(features, name, abbr):
    paths, to_px = build(features, wanted={name}, pad=34)
    if not paths:
        return None
    _, d = paths[0]
    ch = CHAPTERS.get(name, {})
    raw = [(city, *to_px(lon, lat), host) for city, lon, lat, host in ch.get("cities", [])]
    pins = []
    for city, x, y, ly, host in place_labels(raw, dy=20.0, char=8.6, line=19.0):
        leader = ("" if abs(ly - (y - 20)) < 0.6 else
                  f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{ly + 6:.1f}" '
                  f'stroke="{PALETTE["muted"]}" stroke-width="1" opacity=".7"/>')
        pins.append(
            f'<a href="https://{host}/" target="_blank">'
            f'<title>{city} — open the chapter</title>{leader}'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="{PALETTE["live"]}" '
            f'opacity="0.2"><animate attributeName="r" values="11;20;11" dur="3s" '
            f'repeatCount="indefinite"/></circle>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="#fff"/>'
            f'<text x="{x:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="17" '
            f'font-weight="800" fill="{PALETTE["text"]}" stroke="#0f172a" '
            f'stroke-width="3.4" paint-order="stroke" stroke-linejoin="round">'
            f'{city}</text></a>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img"
     aria-label="Map of {name} showing {len(raw)} Move Weight Foundation chapters">
  <style>
    text {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
    a {{ cursor: pointer; }} a:hover text {{ fill: #ff922b; }}
  </style>
  <path d="{d}" fill="{PALETTE['none']}" stroke="{PALETTE['live']}" stroke-width="2.5"/>
  {chr(10).join("  " + p for p in pins)}
</svg>
'''


def main():
    if not GEO.exists():
        raise SystemExit(f"missing {GEO}")
    features = json.loads(GEO.read_text(encoding="utf-8"))["features"]
    OUT.mkdir(parents=True, exist_ok=True)

    f = OUT / "us-expansion.svg"
    f.write_text(us_map(features), encoding="utf-8")
    print(f"  {f.name}  {f.stat().st_size // 1024} KB")

    for name, abbr in (("Oklahoma", "ok"), ("Texas", "tx"), ("Mississippi", "ms")):
        svg = state_map(features, name, abbr)
        if svg:
            p = OUT / f"state-{abbr}.svg"
            p.write_text(svg, encoding="utf-8")
            print(f"  {p.name}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
