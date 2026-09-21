(function () {
  const els = {
    status: document.getElementById("dq-status"),
    toprow: document.getElementById("dq-toprow"),
    tbodyCompleteness: document.querySelector("#dq-completeness-tbl tbody"),
    tbodyRegionMatch: document.querySelector("#dq-region-match-tbl tbody"),
    tbodyMismatch: document.querySelector("#dq-mismatch-tbl tbody"),
    mismatchNote: document.getElementById("dq-mismatch-note"),
    detailsNote: document.getElementById("dq-details-note"),
    issuesRow: document.getElementById("dq-issues-row"),
  };

  const num = (v) => (v ?? 0).toLocaleString();

  function metricCard(lbl, val, sub, kind) {
    return `<div class="col"><div class="card card-lift dq-metric ${kind || ""} h-100"><div class="card-body py-3">
      <div class="lbl">${lbl}</div><div class="val">${val}</div><div class="sub">${sub}</div>
    </div></div></div>`;
  }

  // Wraps a render step so one missing/unexpected field (e.g. the backend
  // hasn't been redeployed with the latest API shape yet) skips just that
  // section instead of blanking the whole page.
  function safe(label, fn) {
    try {
      fn();
    } catch (err) {
      console.warn(`Data Quality: skipped "${label}" —`, err);
    }
  }

  Api.get("/api/v1/data-quality/summary/")
    .then(s => {
      els.status.textContent = `Inspected ${num(s.records_total)} records. Numbers below are computed live from the database.`;
      els.toprow.innerHTML = [
        metricCard("Records total", num(s.records_total), "post-ETL, pre-QA"),
        metricCard("Geocoded", s.geocoded.pct + "%", `${num(s.geocoded.count)} of ${num(s.records_total)}`, s.geocoded.pct >= 85 ? "" : "warn"),
        metricCard("Region matched", s.region_matched.pct + "%", `${num(s.region_matched.count)} of ${num(s.records_total)}`),
        metricCard("District matched", s.district_matched.pct + "%", `${num(s.district_matched.count)} of ${num(s.records_total)}`, s.district_matched.pct >= 75 ? "" : "warn"),
        metricCard("Ward matched", s.ward_matched.pct + "%", `${num(s.ward_matched.count)} of ${num(s.records_total)}`, s.ward_matched.pct >= 75 ? "" : "warn"),
        metricCard("With phone", s.with_phone.pct + "%", `${num(s.with_phone.count)} of ${num(s.records_total)}`, s.with_phone.pct >= 50 ? "" : "bad"),
      ].join("");
    })
    .catch(err => { els.status.textContent = "Failed to load summary: " + err.message; });

  Api.get("/api/v1/data-quality/details/")
    .then(d => {
      const ki = d.known_issues || {};
      const mm = ki.region_mismatches || { total: 0, sample: [] };

      els.detailsNote.textContent =
        `${num(ki.likely_duplicates)} likely duplicate outlets (same name + coordinates); ` +
        `${num(mm.total)} region mismatches; ` +
        `${num(ki.no_region)} outlets with no region on file; ` +
        `${num(ki.no_ward)} with no ward.`;

      safe("field completeness table", () => renderCompletenessTable(d.field_completeness || []));
      safe("field completeness chart", () => renderCompletenessChart(d.field_completeness || []));
      safe("gps source chart", () => renderGpsChart(d.gps_source || { tablet: 0, hand: 0, none: 0 }));
      safe("admin matching chart", () => {
        if (d.admin_matching) renderAdminMatchingChart(d.admin_matching);
        else hideCard("chart-admin-matching");
      });
      safe("geocoding by region chart", () => {
        if (d.geocoding_by_region) renderGeocodeRegionChart(d.geocoding_by_region);
        else hideCard("chart-geocode-region");
      });
      safe("region match table", () => renderRegionMatchTable(d.regions_lowest_district_match || []));
      safe("known issues", () => renderIssues(ki));
      safe("mismatch table", () => renderMismatchTable(mm));
    })
    .catch(err => {
      const restricted = err.message.includes("403");
      document.getElementById("dq-details-section").innerHTML =
        `<div class="alert alert-warning small">${restricted ? "Detailed breakdown is restricted to Data Team accounts." : "Detailed breakdown unavailable: " + err.message + "."}</div>`;
    });

  function hideCard(chartId) {
    const el = document.getElementById(chartId);
    const card = el && el.closest(".card");
    if (card) card.innerHTML = `<div class="card-body text-muted small">Not available yet — the backend needs to be redeployed with the latest API.</div>`;
  }

  function renderCompletenessTable(rows) {
    els.tbodyCompleteness.innerHTML = rows.map(f => `
      <tr>
        <td><strong>${f.label}</strong> <span class="text-muted small">${f.field}</span></td>
        <td class="num">${num(f.filled)}</td>
        <td class="num" style="color:${f.missing ? "#d97706" : "#94a3b8"};">${num(f.missing)}</td>
        <td class="pct">${f.pct.toFixed(1)}%</td>
      </tr>`).join("");
  }

  function renderCompletenessChart(rows) {
    Highcharts.chart("chart-completeness", {
      chart: { type: "bar", height: 320 },
      title: { text: null },
      credits: { enabled: false },
      legend: { enabled: false },
      xAxis: { categories: rows.map(f => f.label), title: { text: null } },
      yAxis: { title: { text: null }, min: 0, max: 100, labels: { format: "{value}%" } },
      tooltip: { pointFormat: "<b>{point.y:.1f}%</b> filled" },
      series: [{
        name: "Filled",
        data: rows.map(f => ({
          y: f.pct,
          color: f.pct >= 95 ? "#0d9488" : f.pct >= 80 ? "#0891b2" : f.pct >= 50 ? "#d97706" : "#dc2626",
        })),
      }],
    });
  }

  function renderGpsChart(gs) {
    Highcharts.chart("chart-gps-source", {
      chart: { type: "pie", height: 300 },
      title: { text: null },
      credits: { enabled: false },
      colors: ["#0d9488", "#0891b2", "#dc2626"],
      plotOptions: { pie: { innerSize: "60%", dataLabels: { enabled: true, format: "{point.name}: {point.percentage:.1f}%" } } },
      legend: { enabled: true, verticalAlign: "bottom" },
      series: [{
        name: "Outlets",
        data: [
          { name: "Tablet GPS", y: gs.tablet || 0 },
          { name: "Hand-held GPS", y: gs.hand || 0 },
          { name: "No coordinates", y: gs.none || 0 },
        ],
      }],
    });
  }

  function renderAdminMatchingChart(m) {
    Highcharts.chart("chart-admin-matching", {
      chart: { type: "bar", height: 300 },
      title: { text: null },
      credits: { enabled: false },
      xAxis: { categories: m.labels, title: { text: null } },
      yAxis: { title: { text: null }, stackLabels: { enabled: false } },
      legend: { enabled: true, verticalAlign: "bottom" },
      plotOptions: { series: { stacking: "normal" } },
      series: [
        { name: "Matched", data: m.matched, color: "#0d9488" },
        { name: "Unmatched", data: m.unmatched, color: "#e2e8f0" },
      ],
    });
  }

  function renderGeocodeRegionChart(rows) {
    Highcharts.chart("chart-geocode-region", {
      chart: { type: "bar", height: Math.max(260, rows.length * 28) },
      title: { text: null },
      credits: { enabled: false },
      legend: { enabled: false },
      xAxis: { categories: rows.map(r => `${r.region} (${r.total})`), title: { text: null } },
      yAxis: { title: { text: null }, min: 0, max: 100, labels: { format: "{value}%" } },
      tooltip: { pointFormat: "<b>{point.y:.1f}%</b> geocoded" },
      series: [{
        name: "Geocoded",
        data: rows.map(r => ({
          y: r.pct,
          color: r.pct >= 90 ? "#0d9488" : r.pct >= 70 ? "#d97706" : "#dc2626",
        })),
      }],
    });
  }

  function renderRegionMatchTable(rows) {
    if (!rows.length) {
      els.tbodyRegionMatch.innerHTML = `<tr><td colspan="4" class="text-muted small text-center py-3">Not available yet.</td></tr>`;
      return;
    }
    els.tbodyRegionMatch.innerHTML = rows.slice(0, 15).map(r => `
      <tr>
        <td><strong>${escapeHtml(r.region)}</strong></td>
        <td class="num">${num(r.total)}</td>
        <td class="num">${num(r.district_matched)}</td>
        <td class="pct">${r.pct.toFixed(1)}%</td>
      </tr>`).join("");
  }

  function renderIssues(ki) {
    els.issuesRow.innerHTML = [
      metricCard("No region on file", num(ki.no_region), "outlets missing a region", ki.no_region ? "warn" : ""),
      metricCard("No ward on file", num(ki.no_ward), "outlets missing a ward", ki.no_ward ? "warn" : ""),
      metricCard("No phone on file", num(ki.no_phone), "outlets missing a phone", ki.no_phone ? "bad" : ""),
      metricCard("Likely duplicates", num(ki.likely_duplicates), "same name + coordinates", ki.likely_duplicates ? "warn" : ""),
    ].join("");
  }

  function renderMismatchTable(mm) {
    const sample = mm.sample || [];
    if (!sample.length) {
      els.tbodyMismatch.innerHTML = `<tr><td colspan="4" class="text-muted small text-center py-3">No region mismatches found.</td></tr>`;
      els.mismatchNote.textContent = "";
      return;
    }
    els.tbodyMismatch.innerHTML = sample.map(r => `
      <tr>
        <td><strong>${escapeHtml(r.name || "—")}</strong> <span class="text-muted small">${escapeHtml(r.addo_uid)}</span></td>
        <td>${escapeHtml(r.submitted_region)}</td>
        <td>${escapeHtml(r.gps_region)}</td>
        <td>${escapeHtml(r.district || "—")}</td>
      </tr>`).join("");
    const total = mm.total || sample.length;
    els.mismatchNote.textContent = total > sample.length
      ? `Showing ${sample.length} of ${num(total)} mismatches.`
      : `${num(total)} mismatch${total === 1 ? "" : "es"} total.`;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
