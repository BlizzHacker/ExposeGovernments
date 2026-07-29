/* Public records letter builder.
 *
 * Runs entirely in the reader's browser. Nothing typed into the form is sent to
 * this server, logged, or persisted — the page says so, and this file is the
 * proof, so keep it that way. There is deliberately no fetch(), no analytics and
 * no storage call anywhere in it.
 *
 * The statute text is substituted at build time from the chapter config, so a
 * Mississippi reader gets seven working days and a free Ethics Commission appeal
 * while a Texas reader gets ten business days and the Attorney General. Getting
 * that wrong tells someone they have no recourse when they do.
 */
(function () {
  "use strict";

  var STATUTE = {
    name: "Mississippi Public Records Act",
    citation: "Miss. Code Ann. § 25-61-1 et seq.",
    responseSection: "§ 25-61-5",
    responseWindow: "seven (7) working days",
    feeSection: "§ 25-61-7",
    feeThreshold: "$25.00",
    appealBody: "Mississippi Ethics Commission",
    city: "Olive Branch",
    state: "Mississippi"
  };

  var $ = function (id) { return document.getElementById(id); };
  var out = $("lf-out");
  if (!out) { return; }

  function today() {
    return new Date().toLocaleDateString(undefined,
      { year: "numeric", month: "long", day: "numeric" });
  }

  function build() {
    var name = ($("lf-name").value || "").trim();
    var email = ($("lf-email").value || "").trim();
    var ask = ($("lf-ask").value || "").trim();
    var range = ($("lf-range").value || "").trim();

    var lines = [];
    lines.push(today());
    lines.push("");
    lines.push("To the Records Custodian, City of " + STATUTE.city);
    lines.push("");
    lines.push("This is a request under the " + STATUTE.name + ", " +
               STATUTE.citation + ".");
    lines.push("");
    lines.push("I request copies of the following records:");
    lines.push("");
    lines.push(ask || "    [Describe the records. Name the document, the body that " +
                      "holds it, and a date range.]");
    if (range) {
      lines.push("");
      lines.push("Date range: " + range + ".");
    }
    lines.push("");

    if ($("lf-electronic").checked) {
      lines.push("Please provide the records in electronic form (PDF or the native " +
                 "file format) by email, which avoids copying charges entirely.");
    }
    if ($("lf-estimate").checked) {
      lines.push("If fulfilling this request will cost more than " +
                 STATUTE.feeThreshold + " (" + STATUTE.feeSection + "), please " +
                 "provide a written estimate before incurring any charge, and I will " +
                 "narrow the request if needed.");
    }
    if ($("lf-itemize").checked) {
      lines.push("If any record or part of a record is withheld, please identify each " +
                 "item withheld and cite the specific statutory exemption relied on for " +
                 "each, and release the remainder.");
    }

    lines.push("");
    lines.push(STATUTE.responseSection + " requires a response within " +
               STATUTE.responseWindow + ". I am noting the date of this request for " +
               "that purpose. If you are not the correct custodian, please forward this " +
               "request and tell me who is.");
    lines.push("");
    lines.push("A denial may be appealed to the " + STATUTE.appealBody + ".");
    lines.push("");
    lines.push("Thank you,");
    lines.push(name || "[Your name]");
    if (email) { lines.push(email); }

    return lines.join("\n");
  }

  function render() { out.textContent = build(); }

  ["lf-name", "lf-email", "lf-ask", "lf-range",
   "lf-electronic", "lf-estimate", "lf-itemize"].forEach(function (id) {
    var el = $(id);
    if (el) { el.addEventListener("input", render); el.addEventListener("change", render); }
  });

  var status = $("lf-status");
  var copy = $("lf-copy");
  if (copy) {
    copy.addEventListener("click", function () {
      var text = build();
      function done(ok) {
        if (!status) { return; }
        status.textContent = ok ? "Copied. Now paste it into your own email."
                                : "Could not copy — select the letter and copy it manually.";
      }
      // navigator.clipboard is unavailable on plain http and in some embedded
      // browsers; the textarea fallback is what makes this work on a phone
      // opened from a link in a text message, which is how a lot of people
      // will actually arrive here.
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { done(true); },
                                                 function () { done(false); });
      } else {
        var ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "absolute";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
        document.body.removeChild(ta);
        done(ok);
      }
    });
  }

  render();
})();
