#!/usr/bin/env python3
"""
Build the statewide hub page for each state domain.

    python3 shared/make_state_hubs.py

exposeoklahoma.com / exposetexas.org / exposemississippi.com are state front
doors. Until now each apex served whichever single city happened to be there,
which leaves nowhere to introduce the second town — the entire reason for moving
to state domains.

A hub page carries the state map, the live chapters, the expansion queue, and the
statute a resident of ANY town in that state can use today. That last part matters
most: the records law is statewide, so someone in a town with no chapter is not
waiting on us to act.

On expansion targets
--------------------
Candidate cities are listed as *places to look*, with the specific public record
that would answer the question. We do NOT assert that a named town has a scandal.
Naming a city next to an accusation we have not documented would be exactly the
thing this project exists to oppose.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "shared" / "assets"

# Candidates are chosen on structural risk — large capital projects, fast growth,
# or a single dominant employer — not on any alleged wrongdoing.
TARGETS = {
    "oklahoma": {
        "why": ("Oklahoma's Open Records Act has no fixed deadline, only a "
                "&ldquo;prompt, reasonable&rdquo; standard, which makes delay the "
                "default tactic and a written record of the delay the best answer."),
        "queue": [
            ("Tulsa &amp; Tulsa County", "Largest metro after OKC. Data-centre and industrial "
             "siting, TIF districts, and county jail contracting."),
            ("Oklahoma City &amp; Cleveland County", "State capital. MAPS programme spending "
             "and economic-development incentives run to hundreds of millions."),
            ("Norman", "University town with rapid annexation and a contested "
             "utility-rate history."),
            ("Ottawa County (beyond Miami)", "Tar Creek Superfund remains the largest "
             "environmental liability in the state."),
            ("Muskogee", "Port and industrial corridor; long-running utility authority."),
        ],
    },
    "texas": {
        "why": ("Texas gives ten business days, but only if a request reaches an address "
                "the body has formally designated &mdash; and many designate none. That "
                "single technicality defeats most citizen requests before they start."),
        "queue": [
            ("Abilene &amp; Taylor County", "Same West Texas water basin as San Angelo, "
             "same data-centre interest, same aquifer pressure."),
            ("Midland &amp; Odessa", "Permian Basin. Enormous property-tax abatements under "
             "Chapter 312/313-successor agreements."),
            ("Lubbock", "Municipal electric utility and a fast-growing load from "
             "industrial siting."),
            ("Waco &amp; McLennan County", "Interstate-35 corridor development and rapid "
             "annexation."),
            ("Tom Green County (beyond San Angelo)", "Appraisal-district valuations that "
             "set every tax bill in the county."),
        ],
    },
    "mississippi": {
        "why": ("Mississippi is the strongest of the three for a citizen: seven working "
                "days to respond, and a denial appeals <strong>free</strong> to the Ethics "
                "Commission, which can order release and fine the official."),
        "queue": [
            ("DeSoto County (beyond Southaven)", "Olive Branch, Horn Lake and Hernando sit "
             "on the same tax base and the same aquifer."),
            ("Jackson &amp; Hinds County", "The capital's water system is under federal "
             "oversight; the contracting record is public."),
            ("Gulfport &amp; Biloxi", "Harrison County. Post-disaster recovery funds and "
             "casino-adjacent development agreements."),
            ("Madison &amp; Rankin Counties", "The fastest-growing suburbs in the state, "
             "with matching infrastructure commitments."),
            ("Tupelo &amp; Lee County", "Long-running industrial recruitment and "
             "fee-in-lieu agreements of the same shape as Southaven's."),
        ],
    },
}

PAGE = """<!--meta
out: state.html
title: {site_name} — public records across {state}
description: The Move Weight Foundation's {state} chapters, the expansion queue, and how any {state} resident can file a public records request today.
-->

<section class="hero">
  <div class="wrap">
    <span class="eyebrow">Statewide &middot; {state}</span>
    <h1>Watching {state}, one county at a time</h1>
    <p class="lede">
      We run city chapters that publish government documents in full. This is the
      statewide view: where we already are, where we are going, and &mdash; most
      importantly &mdash; how to use {state}'s records law yourself, whether or not
      your town has a chapter yet.
    </p>
    <div class="hero-btns">
      <a class="btn btn-red btn-lg" href="/records/">File a records request &rarr;</a>
      <a class="btn btn-ghost btn-lg" href="#queue">Where we are going next</a>
      <a class="btn btn-ghost btn-lg" href="/tips.html">Tell us about your town</a>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="grid2">
      <div>
        <h2>Live chapters</h2>
        {chapter_cards}
        <div class="callout gold">
          <span class="co-label">Why {state} works this way</span>
          <p class="mb0">{why}</p>
        </div>
      </div>
      <div>
        <div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius);padding:18px">
          {map_svg}
        </div>
        <p class="src" style="margin-top:10px">
          Boundaries from public US Census cartographic data, projected
          Albers equal-area.
        </p>
      </div>
    </div>
  </div>
</section>

<section id="queue">
  <div class="wrap">
    <div class="section-head">
      <h2>The expansion queue</h2>
      <p>
        Places we intend to cover next. <strong>These are not accusations.</strong> Each
        is on the list because of its structure &mdash; a large capital project, a
        dominant employer, fast growth, or a big incentive package &mdash; which is
        where public money concentrates and where the documents are worth reading.
        If something is wrong there, the records will show it. If nothing is wrong,
        the records will show that too, and we will publish it either way.
      </p>
    </div>
    <div class="cards">
      {queue_cards}
    </div>
    <div class="callout">
      <span class="co-label">Your town not listed?</span>
      <p class="mb0">
        The queue is not a ranking and it is not fixed. A resident who knows what to
        ask for beats our guess about which county matters every time.
        <a href="/tips.html">Tell us what is happening where you live &rarr;</a>
      </p>
    </div>
  </div>
</section>

<section>
  <div class="wrap narrow">
    <h2>You do not have to wait for us</h2>
    <p>
      {state}'s public records law covers every city, county, school district and
      state agency &mdash; not just the ones we have built a site for. The request we
      would file on your behalf is one you can file yourself today, and we will help
      you write it.
    </p>
    <ol>
      <li><strong>Name a document, not a topic.</strong> &ldquo;All agendas and minutes referencing X between these two dates&rdquo; is hard to refuse. &ldquo;Everything about X&rdquo; invites a denial for being overly broad.</li>
      <li><strong>Put the deadline in the letter.</strong> Citing the statute tells the custodian you know the clock is running.</li>
      <li><strong>Ask for the exemption in writing.</strong> If they withhold, they must say which provision lets them.</li>
      <li><strong>Escalate on paper.</strong> A refusal that exists in writing is the beginning of an appeal, not the end of a request.</li>
    </ol>
    <div class="hero-btns">
      <a class="btn btn-red" href="/records/">Use our request builder &rarr;</a>
      <a class="btn btn-ghost" href="https://foundation.moveweight.com">About the Foundation</a>
    </div>
  </div>
</section>
"""


def main():
    for key in ("oklahoma", "texas", "mississippi"):
        cfgs = [c for c in (ROOT / "chapters").glob("*.json")]
        # A state hub is built into whichever chapter container serves that state.
        by_state = {json.loads(c.read_text(encoding="utf-8"))["state"].lower():
                    json.loads(c.read_text(encoding="utf-8")) for c in cfgs}
        cfg = by_state.get(key)
        if not cfg:
            print(f"  no chapter for {key} — skipped")
            continue

        t = TARGETS[key]
        svg_path = ASSETS / f"state-{cfg['state_abbr'].lower()}.svg"
        svg = svg_path.read_text(encoding="utf-8") if svg_path.exists() else ""

        chapter_cards = (
            f'<div class="card" style="border-color:var(--accent);margin-bottom:14px">'
            f'<div class="card-ico">&#128205;</div>'
            f'<h3>{cfg["city"]}, {cfg["state_abbr"]}</h3>'
            f'<p>{cfg["county"]}. Live chapter with meeting archive, transcripts, '
            f'document library and a records request builder.</p>'
            f'<a class="card-link" href="/">Open the {cfg["city"]} chapter &rarr;</a></div>')

        queue_cards = "\n      ".join(
            f'<div class="card"><h3>{name}</h3><p>{why}</p>'
            f'<a class="card-link" href="/tips.html">Know something here? &rarr;</a></div>'
            for name, why in t["queue"])

        out = ROOT.parent / f"expose{cfg['key']}" / "src" / "pages" / "01-state.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(PAGE.format(
            site_name=cfg["site_name"], state=cfg["state"], why=t["why"],
            map_svg=svg, chapter_cards=chapter_cards, queue_cards=queue_cards,
        ), encoding="utf-8")
        print(f"  {cfg['state']:14s} -> {out.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
