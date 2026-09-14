# Expose network desk

## Scope

This change adds one private operator view for the fourteen Expose chapters,
fixes two records-request status and authentication defects, and restores
cluster-aware automation.

## Inventory and findings

- The canonical ExposeGovernments repository is served from CT 170 at
  `/var/www/exposemiamiok`; nginx serves its `html/` directory.
- The repository remote is `BlizzHacker/ExposeGovernments`.
- Miami had 15 records requests at inspection time: 9 marked sent, 3 rejected,
  2 pending review, and 1 queued. The oldest pending item dated July 15, 2026.
- The Miami records inbox had 4 threads containing 9 messages. Those are private
  and their contents are not included in this report.
- The prior admin API decoded JWTs without verifying signatures and accepted
  tokens based on issuer text. The replacement accepts only the server-issued
  admin secret until full OIDC signature, audience, expiry, and operator-role
  verification is implemented.
- The prior approve action set `sent` after generating a PDF. The replacement
  uses `prepared_for_delivery`; a separate audited action records actual
  delivery and then sets `sent`.
- CT 170 is on `Slimmm`. CTs 175 and 176 moved to `slimmer`, but the weekly
  deploy and chapter-sync jobs still called local `pct`. Both jobs failed on
  September 13, 2026. Cluster-aware routing now relays those fixed calls from
  the approved entry node.
- Thirteen chapter homepages returned HTTPS 200 in the initial sampled check;
  the full collector subsequently returned HTTPS 200 for all fourteen.
- Miami's automation report contained two failed jobs. San Angelo did not
  publish `/data/automation.json`. The dashboard surfaces both conditions
  instead of displaying an all-clear state.

## Admin data model

Legacy request JSON remains the source of public request state. New private
editorial review state lives in a SQLite sidecar keyed by stable queue item ID.
Writes use short `BEGIN IMMEDIATE` transactions and compare-and-swap versions;
a stale editor receives HTTP 409. The dashboard loads at most 100 items and
never starts collection work.

## Verification

- Four Flask API regression tests cover unsigned-token rejection, distinct PDF
  preparation and delivery states, optimistic concurrency, and the fixed
  fourteen-chapter inventory.
- Python compilation passed for the API, collector, provisioner, and sync job.
- JavaScript syntax validation passed for the dashboard.
- A live read-only collector run returned fourteen chapters and a Miami queue
  aggregate of 15 total and 2 pending without exposing submission contents.
- The collector timer is enabled and active; its latest one-shot run exited 0
  after checking all fourteen public hosts and copying only the aggregate
  snapshot into CT 170.
- A cross-node temporary-file probe exercised the provisioner's real `pct push`
  path for CT 175 through `root@slimmer` and passed. The temporary file was
  removed from both nodes after the assertion.
- The all-city mirror read 22.7 MB from thirteen chapter web roots, committed
  the result from an isolated worktree, and pushed GitHub `main` at
  `b64e2b5c26f01cf5fb1c363db353bb10b2f9984a`.
- Live browser checks found the Miami homepage and private dashboard login
  rendered and reachable over HTTPS.
- The repaired weekly run completed eleven maintained chapter pipelines and
  their deployments with zero failed steps. Its internal-link crawl checked
  299 links across eighteen hosts and found zero broken links.
- Miami's video generator now skips and reports malformed upload markers rather
  than aborting the full hourly run. The verification run rebuilt 528 video
  records and finished with zero failed jobs.
- San Angelo's nginx policy now exposes only the public automation-status JSON
  alongside the search index while keeping the rest of `/data/` closed.
- The final collector pass reported fourteen of fourteen chapter homepages
  healthy and fourteen of fourteen automation reports available with no active
  issue.

## Queue review

The two old pending requests now carry `needs_records` review notes explaining
their scope, privacy, or custodian problems. The previously queued City Attorney
request is `in_review` until its recipient and actual delivery can be verified.
Private investigation drafts are `in_review` with an instruction to confirm the
correct custodian, channel, date range, and agency form. No draft or PDF was
marked sent merely because it was prepared.

Investigation research and drafts are kept outside the public webroot. The
public homepage contains no investigation feature, and the former public route
returns HTTP 404.
