#!/usr/bin/env python3
"""Publish the live status of the Foundation's open records requests to Miami.

    python3 /opt/records_status.py

Rendered fresh rather than typed once, because the only number on it that moves
is the day count, and a hand-written "18 days ago" is wrong by tomorrow. Run
daily by miami-refresh.timer.

What is on this block is limited to what the record supports:

* Six request forms, delivered by hand on Friday 10 July 2026. The cover letter
  emailed the day before (Thu 9 July, 3:18 PM) lists all six and states they
  would be handed over in person the next day.
* Two of the six cover the same ground - City social media records, and a full
  digital export of the same accounts - so there are five distinct subjects.
* The City Clerk's reply of 10 July states the City no longer accepts open
  records requests by email "per direction of legal counsel", and that a
  requester must come in or mail the form.

Deliberately NOT on this block:

* The names of the individual officials whose records were requested. The
  subjects are described by office. Naming a person on a homepage beside the
  words "records requested" implies suspicion of that person, and this project's
  own pages say a chapter is opened on structural risk, not on an accusation.
* Any claim that the City is late. 51 O.S. Sec. 24A.5 requires "prompt,
  reasonable" access and sets no fixed number of days. The elapsed count is
  stated as a fact and left to the reader.

The counter runs live in the reader's browser from about 4pm Central on Friday
10 July 2026 - the time Wade delivered the forms in writing, given first-hand.
It is written as 16:00 and described as "about 4pm" rather than a precise
minute, because the minute is not recorded and a clock whose point is that it
is checkable should not carry invented precision.
"""

import pathlib
import re
from datetime import date

OUT = pathlib.Path("/var/www/exposemiamiok/html/index.html")
START = "<!-- RECORDS REQUESTS START -->"
END = "<!-- RECORDS REQUESTS END -->"

DELIVERED = date(2026, 7, 10)          # Friday - handed over at the City Clerk's office
# ISO 8601 with the Central offset, read by the browser.
DELIVERED_AT = "2026-07-10T16:00:00-05:00"
EMAILED = date(2026, 7, 9)             # cover letter listing all six

SUBJECTS = [
    "City Council minutes and resolutions, January 2026 to present, including executive session records",
    "City social media records across all platforms, and the City&rsquo;s social media policy",
    "Animal control policies, procedures and incident records",
    "Employment records held by the City for the office of City Attorney",
    "A complete digital export of the City&rsquo;s social media accounts "
    "<span class=\"rr-dup\">(covers the same ground as the second request)</span>",
    "Communications between a council member and the Mayor, January 2025 to June 2026",
]


def block(today=None):
    today = today or date.today()
    days = (today - DELIVERED).days
    weeks = days // 7
    ago = (f"{days} days ago" if days < 14
           else f"{weeks} weeks ago" if days % 7 == 0
           else f"just over {weeks} weeks ago")
    items = "\n".join(f"      <li>{s}</li>" for s in SUBJECTS)
    # "%-d" is a glibc extension and raises on Windows, where this file is also
    # edited and syntax-checked. Built by hand so it works in both places.
    stamp = f"{today.day} {today.strftime('%B %Y')}"
    return f"""{START}
<section id="records-requested" class="rr">
  <p class="rr-eyebrow">Open records &mdash; where things stand</p>
  <h2 class="rr-h">Six records requests are with the City of Miami</h2>

  <div class="rr-clock" data-since="{DELIVERED_AT}" aria-live="off">
    <div class="rr-since">Time since we handed them in</div>
    <div class="rr-dials">
      <div class="rr-dial"><span class="rr-n" data-u="d">{days}</span><span class="rr-l">days</span></div>
      <div class="rr-sep">:</div>
      <div class="rr-dial"><span class="rr-n" data-u="h">00</span><span class="rr-l">hrs</span></div>
      <div class="rr-sep">:</div>
      <div class="rr-dial"><span class="rr-n" data-u="m">00</span><span class="rr-l">min</span></div>
      <div class="rr-sep">:</div>
      <div class="rr-dial"><span class="rr-n rr-s" data-u="s">00</span><span class="rr-l">sec</span></div>
    </div>
    <div class="rr-from">counting from about 4pm on <strong>Friday, 10&nbsp;July&nbsp;2026</strong></div>
  </div>

  <p class="rr-p">
    We hand-delivered six completed Open Records Request forms, in writing, to
    the City Clerk&rsquo;s office late on the afternoon of Friday
    10&nbsp;July&nbsp;2026. Two of the six cover the same ground, so there are
    five distinct subjects.
  </p>
  <ul class="rr-list">
{items}
  </ul>
  <p class="rr-p">
    We emailed a cover letter listing all six the day before. The City Clerk
    replied that, <em>per direction of legal counsel</em>, the City no longer
    accepts open records requests by email and that a requester must come in or
    post the form. That is why these were delivered by hand.
  </p>
  <p class="rr-p rr-status">
    <strong>Status:</strong> in a telephone call, the City Clerk told us the
    requests are being processed by each department.
    <strong>No fee estimate and no records have arrived yet.</strong> When they
    do, they are published here whole and unredacted, and this clock stops.
  </p>
  <p class="rr-note">
    Oklahoma&rsquo;s Open Records Act (51&nbsp;O.S. &sect;&nbsp;24A.5) requires
    prompt and reasonable access; it sets <strong>no</strong> fixed number of
    days. This clock states elapsed time. It is not a countdown, and it is not a
    claim that the City is late.
  </p>
</section>

<style>
.rr{{border:1px solid var(--border);border-radius:10px;padding:1.15rem 1.3rem;
 margin:1rem 0 1.4rem;background:linear-gradient(135deg,rgba(127,29,29,.92),rgba(15,23,42,.96))}}
.rr-eyebrow{{margin:0 0 .35rem;color:#cbd5e1;font-weight:800;text-transform:uppercase;
 letter-spacing:.08em;font-size:.78rem}}
.rr-h{{margin:.1rem 0 .9rem}}
.rr-clock{{background:rgba(0,0,0,.28);border:1px solid rgba(255,255,255,.10);
 border-radius:10px;padding:.85rem 1rem;margin:0 0 1rem;text-align:center}}
.rr-since{{color:#cbd5e1;font-size:.74rem;text-transform:uppercase;
 letter-spacing:.09em;font-weight:700;margin-bottom:.45rem}}
.rr-dials{{display:flex;align-items:flex-start;justify-content:center;gap:.35rem}}
.rr-dial{{display:flex;flex-direction:column;align-items:center;min-width:3.4rem}}
.rr-n{{font-size:clamp(1.9rem,6vw,2.9rem);font-weight:800;line-height:1;color:#fff;
 font-variant-numeric:tabular-nums;font-family:ui-monospace,"SF Mono",Consolas,monospace}}
.rr-l{{font-size:.66rem;text-transform:uppercase;letter-spacing:.1em;color:#cbd5e1;
 margin-top:.3rem;font-weight:700}}
.rr-sep{{font-size:clamp(1.4rem,4vw,2.1rem);color:rgba(255,255,255,.35);line-height:1.1}}
.rr-s{{transition:opacity .25s ease}}
.rr-tick{{opacity:.55}}
@media (prefers-reduced-motion:reduce){{.rr-s{{transition:none}}.rr-tick{{opacity:1}}}}
.rr-from{{color:#cbd5e1;font-size:.78rem;margin-top:.5rem}}
.rr-p{{margin:0 0 .7rem}}
.rr-list{{margin:0 0 .8rem;padding-left:1.15rem;line-height:1.65}}
.rr-dup{{color:#cbd5e1;font-size:.9em}}
.rr-status{{margin-bottom:.2rem}}
.rr-note{{margin:.6rem 0 0;font-size:.86rem;color:#cbd5e1}}
</style>

<script>
(function(){{
  var el=document.getElementById('records-requested');
  if(!el)return;
  var c=el.querySelector('.rr-clock'), from=new Date(c.dataset.since).getTime();
  if(isNaN(from))return;
  var f={{}};['d','h','m','s'].forEach(function(u){{f[u]=c.querySelector('[data-u="'+u+'"]')}});
  var pad=function(n){{return(n<10?'0':'')+n}};
  function tick(){{
    var t=Math.max(0,Date.now()-from), s=Math.floor(t/1000);
    f.d.textContent=Math.floor(s/86400);
    f.h.textContent=pad(Math.floor(s/3600)%24);
    f.m.textContent=pad(Math.floor(s/60)%60);
    f.s.textContent=pad(s%60);
    f.s.classList.add('rr-tick');
    setTimeout(function(){{f.s.classList.remove('rr-tick')}},220);
  }}
  tick();setInterval(tick,1000);
}})();
</script>
{END}"""


def main():
    html = OUT.read_text(encoding="utf-8")
    new = block()
    if START in html and END in html:
        html = re.sub(re.escape(START) + r".*?" + re.escape(END),
                      lambda _: new, html, flags=re.S)
        how = "updated"
    else:
        anchor = '<main id="main">'
        if anchor not in html:
            raise SystemExit("could not find <main id=\"main\"> on the homepage")
        html = html.replace(anchor, anchor + "\n\n" + new, 1)
        how = "inserted"
    OUT.write_text(html, encoding="utf-8")
    print(f"records status {how}: {(date.today() - DELIVERED).days} days since delivery")


if __name__ == "__main__":
    main()
