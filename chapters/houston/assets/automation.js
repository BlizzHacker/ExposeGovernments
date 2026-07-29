/* Renders /data/automation.json into the "What is stale" table.
 *
 * The contract with the weekly runner is deliberately small:
 *
 *   { "generated_at": ISO8601,
 *     "jobs": [ { "name", "what", "last_run", "ok", "detail" } ] }
 *
 * `ok` is a boolean and `last_run` may be null for a job that has never run.
 * Both of those states are rendered honestly rather than hidden: a job that has
 * never run is not "fine", it is unknown, and the page says unknown.
 *
 * Staleness is computed here, in the reader's browser, from last_run — not
 * written into the file by the job. A job that dies cannot update its own status
 * to say it died, so a status file that is itself out of date must still be able
 * to produce a red row. That is the whole reason this page exists.
 */
(function () {
  "use strict";

  var STALE_DAYS = 9;      // weekly cadence plus two days of slack
  var VERY_STALE_DAYS = 21;

  var tbody = document.querySelector("#auto-table tbody");
  var summary = document.getElementById("auto-summary-text");
  var box = document.getElementById("auto-summary");
  if (!tbody) { return; }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function daysSince(iso) {
    if (!iso) { return null; }
    var t = Date.parse(iso);
    if (isNaN(t)) { return null; }
    return (Date.now() - t) / 86400000;
  }

  function ago(iso) {
    var d = daysSince(iso);
    if (d === null) { return "never"; }
    if (d < 1) { return "today"; }
    if (d < 2) { return "yesterday"; }
    return Math.floor(d) + " days ago";
  }

  function classify(job) {
    var d = daysSince(job.last_run);
    if (d === null) { return { cls: "st-unknown", label: "never run" }; }
    if (job.ok === false) { return { cls: "st-bad", label: "failed" }; }
    if (d > VERY_STALE_DAYS) { return { cls: "st-bad", label: "very stale" }; }
    if (d > STALE_DAYS) { return { cls: "st-warn", label: "stale" }; }
    return { cls: "st-ok", label: "current" };
  }

  function render(data) {
    var jobs = (data && data.jobs) || [];
    if (!jobs.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="dim">No jobs have reported yet. ' +
        'The weekly timer publishes this file on its first run.</td></tr>';
      if (summary) {
        summary.textContent = "This chapter's automation has not reported a run yet.";
      }
      return;
    }

    var rows = jobs.map(function (j) {
      var s = classify(j);
      return "<tr>" +
        "<td><strong>" + esc(j.name) + "</strong></td>" +
        "<td>" + esc(j.what) + "</td>" +
        "<td>" + esc(ago(j.last_run)) +
        (j.last_run ? '<br><span class="dim small">' + esc(j.last_run) + "</span>" : "") +
        "</td>" +
        '<td><span class="status ' + s.cls + '">' + s.label + "</span></td>" +
        '<td class="dim">' + esc(j.detail || "") + "</td>" +
        "</tr>";
    });
    tbody.innerHTML = rows.join("");

    var bad = jobs.filter(function (j) { return classify(j).cls === "st-bad"; }).length;
    var warn = jobs.filter(function (j) { return classify(j).cls === "st-warn"; }).length;
    if (summary) {
      if (bad) {
        summary.innerHTML = "<strong>" + bad + " of " + jobs.length +
          " jobs are failing or very stale.</strong> Parts of this site are out of date. " +
          "The rows below say which.";
        if (box) { box.className = "callout red"; }
      } else if (warn) {
        summary.innerHTML = warn + " of " + jobs.length +
          " jobs are running behind schedule. Nothing is broken; the archive is not " +
          "fully current.";
        if (box) { box.className = "callout gold"; }
      } else {
        summary.innerHTML = "All " + jobs.length +
          " jobs ran on schedule. Last report: " + esc(ago(data.generated_at)) + ".";
        if (box) { box.className = "callout"; }
      }
    }
  }

  fetch("/data/automation.json", { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    })
    .then(render)
    .catch(function () {
      // A missing status file is itself a status. Saying "loading" forever, or
      // showing nothing, would be the dishonest option.
      tbody.innerHTML = '<tr><td colspan="5" class="dim">Could not read the status ' +
        'file. Either the weekly job has never completed on this chapter, or the ' +
        'file is not being published — both mean the archive below may be out of ' +
        'date.</td></tr>';
      if (summary) {
        summary.textContent = "Status file unavailable — treat this chapter's archive as " +
          "possibly out of date.";
      }
      if (box) { box.className = "callout red"; }
    });
})();
