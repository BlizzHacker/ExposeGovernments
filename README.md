# ExposeGovernments

A project of the [Move Weight Foundation](https://foundation.moveweight.com), a
501(c)(3).

Fourteen city chapters across Oklahoma, Texas and Mississippi. Each one indexes
what its local government actually did — the meeting, the agenda packet, the
minutes, the video — from the city's own portal, and publishes it whole, with a
link back to the source so anyone can check it.

Public records are already public. Mostly nobody has them, because they are
scattered across portals that paginate badly, expire, and quietly go dark. That
is the gap this fills.

## The chapters

| City | Site |
|---|---|
| Miami, OK | [miami.exposeoklahoma.com](https://miami.exposeoklahoma.com) |
| Oklahoma City, OK | [okc.exposeoklahoma.com](https://okc.exposeoklahoma.com) |
| Tulsa, OK | [tulsa.exposeoklahoma.com](https://tulsa.exposeoklahoma.com) |
| Claremore, OK | [claremore.exposeoklahoma.com](https://claremore.exposeoklahoma.com) |
| San Angelo, TX | [sanangelo.exposetexas.org](https://sanangelo.exposetexas.org) |
| Houston, TX | [houston.exposetexas.org](https://houston.exposetexas.org) |
| Dallas, TX | [dallas.exposetexas.org](https://dallas.exposetexas.org) |
| Austin, TX | [austin.exposetexas.org](https://austin.exposetexas.org) |
| San Antonio, TX | [sanantonio.exposetexas.org](https://sanantonio.exposetexas.org) |
| Lubbock, TX | [lubbock.exposetexas.org](https://lubbock.exposetexas.org) |
| Abilene, TX | [abilene.exposetexas.org](https://abilene.exposetexas.org) |
| Southaven, MS | [southaven.exposemississippi.com](https://southaven.exposemississippi.com) |
| Jackson, MS | [jackson.exposemississippi.com](https://jackson.exposemississippi.com) |
| Olive Branch, MS | [olivebranch.exposemississippi.com](https://olivebranch.exposemississippi.com) |

5,423 public meetings indexed across all fourteen as of 29 July 2026. The live
count is on the [chapter directory](https://foundation.moveweight.com/#chapter-directory),
which is generated from the chapters themselves and cannot drift from them.

## What is in this repository

The published site of every chapter.

```
html/        Miami, Oklahoma — the first chapter, and the only one whose site is
             hand-maintained rather than generated from the shared template
mirror/      a dated copy of the City of Miami's own pages, kept because a city
             can retire a page and the public loses it — each carries a banner
             naming it a copy and linking the live original
data/, ops/  Miami's indexes and operational scripts
chapters/    the other thirteen, one directory per city, synced from the
             containers that serve them

rebuild_meetings_page.py, rebuild_all.py
             rebuild Miami's meeting archive and its per-meeting pages
```

Miami sits at the root rather than under `chapters/` for a blunt reason: this
repository's root **is** its live webroot, and `html/` is the directory nginx
serves. Moving it for the sake of a tidier tree would move the files being
served. The asymmetry is honest about how the thing is actually deployed.

**Media is excluded** — no mp4, wav, mp3 or pdf. Miami's webroot alone is 84 GB,
almost all of it meeting video; what belongs in version control is the published
record, not the raw footage. Transcripts of that video are here.

Commits titled "Rebuild meetings index" are automated. Archives refresh on
timers and each site publishes its own staleness — Miami's is at
[/automation-status.html](https://miami.exposeoklahoma.com/automation-status.html),
including the jobs that failed.

## How we handle the records

- **Published whole.** Records come back as they came back. We do not redact and
  we do not excerpt to taste. Every document links to the issuing body's own
  copy so the reader can check us against the source.
- **Nothing here is an accusation.** A chapter is opened where the structure
  makes a problem likely — money moving through few hands, a consent agenda
  nobody reads, a utility with no competitor — not because we have concluded
  anyone did anything. Where a record raises a question, the question is stated
  as a question.
- **Requesters stay anonymous.** Requests are filed in the Foundation's name.
  A submitter's identity is never published — not in a page, not in a filename,
  not in metadata.
- **Government contact details are transcribed, never invented**, and dated.

## Funding

Each chapter has its own fundraiser so donations are attributable to the area
that earned them, and so "which city do people actually want watched" has an
answer. The directory carries a link per city:
[foundation.moveweight.com/#chapter-directory](https://foundation.moveweight.com/#chapter-directory).

Records requests cost money — bodies bill per page, per hour of staff time, per
certified stamp, and you do not learn the price until after you ask. That is
what the money is for.

## Contact

Tips and corrections: **team@moveweight.com**. You do not have to say who you
are. If a link here is dead or a fact is wrong, tell us and we will fix it and
say that we did.
