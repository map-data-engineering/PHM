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

  function metricCard(lbl, val, sub, kind) {
    return `<div class="col"><div class="card card-lift dq-metric ${kind || ""} h-100"><div class="card-body py-3">
      <div class="lbl">${lbl}</div><div class="val">${val}</div><div class="sub">${sub}</div>
    </div></div></div>`;
  }

  Api.get("/api/v1/data-quality/summary/")
    .then(s => {
      els.status.textContent = `Inspected ${s.records_total.toLocaleString()} records. Numbers below are computed live from the database.`;
      els.toprow.innerHTML = [
        metricCard("Records total", s.records_total.toLocaleString(), "post-ETL, pre-QA"),
        metricCard("Geocoded", s.geocoded.pct + "%", `${s.geocoded.count.toLocaleString()} of ${s.records_total.toLocaleString()}`, s.geocoded.pct >= 85 ? "" : "warn"),
        metricCard("Region matched", s.region_matched.pct + "%", `${s.region_matched.count.toLocaleString()} of ${s.records_total.toLocaleString()}`),
        metricCard("District matched", s.district_matched.pct + "%", `${s.district_matched.count.toLocaleString()} of ${s.records_total.toLocaleString()}`, s.district_matched.pct >= 75 ? "" : "warn"),
        metricCard("Ward matched", s.ward_matched.pct + "%", `${s.ward_matched.count.toLocaleString()} of ${s.records_total.toLocaleString()}`, s.ward_matched.pct >= 75 ? "" : "warn"),
        metricCard("With phone", s.with_phone.pct + "%", `${s.with_phone.count.toLocaleString()} of ${s.records_total.toLocaleString()}`, s.with_phone.pct >= 50 ? "" : "bad"),
      ].join("");
    })
    .catch(err => { els.status.textContent = "Failed to load summary: " + err.message; });

  Api.get("/api/v1/data-quality/details/")
    .then(d => {
      const mm = d.known_issues.region_mismatches;
      els.detailsNote.textContent =
        `${d.known_issues.likely_duplicates.toLocaleString()} likely duplicate outlets (same name + coordinates); ` +
        `${mm.total.toLocaleString()} region mismatches; ` +
        `${d.known_issues.no_region.toLocaleString()} outlets with no region on file; ` +
        `${d.known_issues.no_ward.toLocaleString()} with no ward.`;

      renderCompletenessTable(d.field_completeness);
      renderCompletenessChart(d.field_completeness);
      renderGpsChart(d.gps_source);
      renderAdminMatchingChart(d.admin_matching);
      renderGeocodeRegionChart(d.geocoding_by_region);
      renderRegionMatchTable(d.regions_lowest_district_match);
      renderIssues(d.known_issues);
      renderMismatchTable(mm);
    })
    .catch(err => {
      const restricted = err.message.includes("403");
      document.getElementById("dq-details-section").innerHTML =
        `<div class="alert alert-warning small">${restricted ? "Detailed breakdown is restricted to Data Team accounts." : "Detailed breakdown unavailable: " + err.message + "."}</div>`;
    });

  function renderCompletenessTable(rows) {
    els.tbodyCompleteness.innerHTML = rows.map(f => `
      <tr>
        <td><strong>${f.label}</strong> <span class="text-muted small">${f.field}</span></td>
        <td class="num">${f.filled.toLocaleString()}</td>
        <td class="num" style="color:${f.missing ? "#d97706" : "#94a3b8"};">${f.missing.toLocaleString()}</td>
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
          { name: "Tablet GPS", y: gs.tablet },
          { name: "Hand-held GPS", y: gs.hand },
          { name: "No coordinates", y: gs.none },
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
    els.tbodyRegionMatch.innerHTML = rows.slice(0, 15).map(r => `
      <tr>
        <td><strong>${escapeHtml(r.region)}</strong></td>
        <td class="num">${r.total.toLocaleString()}</td>
        <td class="num">${r.district_matched.toLocaleString()}</td>
        <td class="pct">${r.pct.toFixed(1)}%</td>
      </tr>`).join("");
  }

  function renderIssues(ki) {
    els.issuesRow.innerHTML = [
      metricCard("No region on file", ki.no_region.toLocaleString(), "outlets missing a region", ki.no_region ? "warn" : ""),
      metricCard("No ward on file", ki.no_ward.toLocaleString(), "outlets missing a ward", ki.no_ward ? "warn" : ""),
      metricCard("No phone on file", ki.no_phone.toLocaleString(), "outlets missing a phone", ki.no_phone ? "bad" : ""),
      metricCard("Likely duplicates", ki.likely_duplicates.toLocaleString(), "same name + coordinates", ki.likely_duplicates ? "warn" : ""),
    ].join("");
  }

  function renderMismatchTable(mm) {
    if (!mm.sample.length) {
      els.tbodyMismatch.innerHTML = `<tr><td colspan="4" class="text-muted small text-center py-3">No region mismatches found.</td></tr>`;
      els.mismatchNote.textContent = "";
      return;
    }
    els.tbodyMismatch.innerHTML = mm.sample.map(r => `
      <tr>
        <td><strong>${escapeHtml(r.name || "—")}</strong> <span class="text-muted small">${escapeHtml(r.addo_uid)}</span></td>
        <td>${escapeHtml(r.submitted_region)}</td>
        <td>${escapeHtml(r.gps_region)}</td>
        <td>${escapeHtml(r.district || "—")}</td>
      </tr>`).join("");
    els.mismatchNote.textContent = mm.total > mm.sample.length
      ? `Showing ${mm.sample.length} of ${mm.total.toLocaleString()} mismatches.`
      : `${mm.total.toLocaleString()} mismatch${mm.total === 1 ? "" : "es"} total.`;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
