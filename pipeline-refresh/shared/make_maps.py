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

# Where the Foundation actually operates, and where it is heading.
CHAPTERS = {
    "Oklahoma":    {"status": "live", "url": "https://exposeoklahoma.com/state.html",
                   "cities": [("Miami", -94.8774, 36.8742, "https://miami.exposeoklahoma.com")]},
    "Texas":       {"status": "live", "url": "https://exposetexas.org/state.html",
                   "cities": [("San Angelo", -100.4370, 31.4638, "https://sanangelo.exposetexas.org")]},
    "Mississippi": {"status": "live", "url": "https://exposemississippi.com/state.html",
                   "cities": [("Southaven", -89.9987, 34.9890, "https://southaven.exposemississippi.com")]},
}

PALETTE = {
    "live":    "#e8590c",
    "next":    "#f0a020",
    "none":    "#1b2130",
    "stroke":  "#2c3547",
    "text":    "#eef2f8",
    "muted":   "#6f7d95",
}

W, H = 1000, 620

# Alaska spans ~2400km and crosses the antimeridian; Hawaii sits 3700km out to
# sea. Fitting one bounding box across all 52 features squashed the lower 48
# into a corner and made the map useless. Every serious US map insets these.
NON_CONUS = {"Alaska", "Hawaii", "Puerto Rico"}


def albers(lon, lat):
    """Albers equal-area conic, USA standard parallels."""
    lon0, lat0 = math.radians(-96.0), math.radians(37.5)
    p1, p2 = math.radians(29.5), math.radians(45.5)
    lon, lat = math.radians(lon), math.radians(lat)
    n = 0.5 * (math.sin(p1) + math.sin(p2))
    if abs(n) < 1e-9:
        n = 1e-9
    C = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
    rho0 = math.sqrt(C - 2 * n * math.sin(lat0)) / n
    val = C - 2 * n * math.sin(lat)
    rho = math.sqrt(max(val, 0)) / n
    theta = n * (lon - lon0)
    # SVG y grows downward but Albers y grows north, so negate: without this
    # the whole country renders upside down and every city pin lands in the
    # wrong state.
    return rho * math.sin(theta), -(rho0 - rho * math.cos(theta))


def rings(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return [c[0]]
    if t == "MultiPolygon":
        return [p[0] for p in c]
    return []


def build(features, wanted=None, pad=24, skip=None):
    """Project, fit to the viewbox, and return per-state SVG paths."""
    pts, prepared = [], []
    for f in features:
        name = f["properties"]["name"]
        if wanted and name not in wanted:
            continue
        if skip and name in skip:
            continue
        polys = []
        for ring in rings(f["geometry"]):
            xy = [albers(lon, lat) for lon, lat in ring]
            if len(xy) > 3:
                polys.append(xy)
                pts.extend(xy)
        if polys:
            prepared.append((name, polys))
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
        d = []
        for ring in polys:
            # Drop near-duplicate points: the source data is far denser than a
            # 1000px canvas can show, and the raw file is 89 KB of noise.
            pxs, last = [], None
            for x, y in ring:
                px, py = x * scale + ox, y * scale + oy
                if last and abs(px - last[0]) < 0.45 and abs(py - last[1]) < 0.45:
                    continue
                pxs.append((px, py))
                last = (px, py)
            if len(pxs) > 3:
                d.append("M" + " ".join(f"{x:.1f},{y:.1f}" for x, y in pxs) + "Z")
        if d:
            out.append((name, " ".join(d)))
    return out, to_px


def _fit(features, names, w, h, ox, oy, pad=6):
    """Project a subset into its own box. Returns (paths, to_px)."""
    pts, prepared = [], []
    for f in features:
        if f["properties"]["name"] not in names:
            continue
        polys = []
        for ring in rings(f["geometry"]):
            xy = [albers(lon, lat) for lon, lat in ring
                  if not (f["properties"]["name"] == "Alaska" and lon > 0)]
            if len(xy) > 3:
                polys.append(xy)
                pts.extend(xy)
        if polys:
            prepared.append((f["properties"]["name"], polys))
    if not pts:
        return [], None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    sc = min((w - 2 * pad) / max(maxx - minx, 1e-9), (h - 2 * pad) / max(maxy - miny, 1e-9))
    dx = ox + (w - (maxx - minx) * sc) / 2 - minx * sc
    dy = oy + (h - (maxy - miny) * sc) / 2 - miny * sc

    def to_px(lon, lat):
        x, y = albers(lon, lat)
        return x * sc + dx, y * sc + dy

    out = []
    for name, polys in prepared:
        d = []
        for ring in polys:
            pxs, last = [], None
            for x, y in ring:
                px, py = x * sc + dx, y * sc + dy
                if last and abs(px - last[0]) < 0.45 and abs(py - last[1]) < 0.45:
                    continue
                pxs.append((px, py))
                last = (px, py)
            if len(pxs) > 3:
                d.append("M" + " ".join(f"{a:.1f},{b:.1f}" for a, b in pxs) + "Z")
        if d:
            out.append((name, " ".join(d)))
    return out, to_px


def us_map(features):
    conus = {f["properties"]["name"] for f in features} - NON_CONUS
    body, markers = [], []

    groups = [
        (conus, W, H - 40, 0, 0, 24),
        ({"Alaska"}, 210, 150, 18, H - 178, 6),
        ({"Hawaii"}, 130, 90, 240, H - 118, 6),
    ]
    projections = {}
    for names, w, h, ox, oy, pad in groups:
        paths, to_px = _fit(features, names, w, h, ox, oy, pad)
        for name, d in paths:
            ch = CHAPTERS.get(name)
            fill = PALETTE[ch["status"]] if ch else PALETTE["none"]
            path = (f'<path class="st{" live" if ch else ""}" d="{d}" fill="{fill}" '
                    f'stroke="{PALETTE["stroke"]}" stroke-width="0.8"><title>{name}'
                    f'{" — chapter live, click to open" if ch else " — no chapter yet"}'
                    f'</title></path>')
            if ch and ch.get("url"):
                path = (f'<a href="{ch["url"]}" target="_top" '
                        f'aria-label="Open the {name} chapter">{path}</a>')
            body.append(path)
        for n in names:
            projections[n] = to_px

    for name, ch in CHAPTERS.items():
        to_px = projections.get(name)
        if not to_px:
            continue
        for city, lon, lat, curl in ch["cities"]:
            x, y = to_px(lon, lat)
            markers.append(
                f'<a href="{curl}" target="_top" aria-label="Open the {city} chapter">'
                f'<g class="pin"><title>{city} — open the chapter</title>'
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" '
                f'fill="{PALETTE["live"]}" opacity="0.22"><animate attributeName="r" '
                f'values="9;17;9" dur="3s" repeatCount="indefinite"/></circle>'
                # A generous transparent disc: a 4.5px dot is not a tap target.
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="18" fill="transparent"/>'
                f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#fff"/>'
                f'<text x="{x:.1f}" y="{y - 16:.1f}" text-anchor="middle" font-size="13" '
                f'font-weight="700" fill="{PALETTE["text"]}" '
                f'style="paint-order:stroke;stroke:#0c0f14;stroke-width:3px">{city}</text>'
                f'</g></a>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img"
     aria-label="Map of the United States showing Move Weight Foundation chapters in {", ".join(CHAPTERS)}">
  <style>
    .st {{ transition: fill .2s; }}
    .st.live {{ cursor: pointer; }}
    a:hover .st.live {{ fill: #ff922b; }}
    .pin {{ cursor: pointer; }}
    .pin .dot {{ transition: r .15s; }}
    a:hover .pin .dot {{ r: 7; }}
    a:focus-visible .st.live, a:focus-visible .pin .dot {{ outline: 2px solid #fff; }}
    text {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
  </style>
  {chr(10).join("  " + b for b in body)}
  {chr(10).join("  " + m for m in markers)}
  <g transform="translate({W - 250},{H - 60})">
    <rect x="0" y="0" width="14" height="14" rx="3" fill="{PALETTE['live']}"/>
    <text x="21" y="12" font-size="13" fill="{PALETTE['text']}">3 states with a live chapter</text>
    <rect x="0" y="22" width="14" height="14" rx="3" fill="{PALETTE['none']}" stroke="{PALETTE['stroke']}"/>
    <text x="21" y="34" font-size="13" fill="{PALETTE['muted']}">47 states still unwatched</text>
  </g>
</svg>
'''


def state_map(features, name, abbr):
    paths, to_px = build(features, wanted={name}, pad=34)
    if not paths:
        return None
    _, d = paths[0]
    ch = CHAPTERS.get(name, {})
    pins = []
    for city, lon, lat, curl in ch.get("cities", []):
        x, y = to_px(lon, lat)
        pins.append(
            f'<a href="{curl}" target="_top" aria-label="Open the {city} chapter">'
            f'<g class="pin"><title>{city} — open the chapter</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="18" fill="transparent"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" fill="{PALETTE["live"]}" '
            f'opacity="0.2"><animate attributeName="r" values="12;22;12" dur="3s" '
            f'repeatCount="indefinite"/></circle>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#fff"/>'
            f'<text x="{x:.1f}" y="{y - 20:.1f}" text-anchor="middle" font-size="17" '
            f'font-weight="800" fill="{PALETTE["text"]}">{city}</text></g></a>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img"
     aria-label="Map of {name} showing Move Weight Foundation coverage">
  <style>text {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
  .pin {{ cursor: pointer; }}</style>
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
