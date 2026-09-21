(function () {
  const els = {
    status: document.getElementById("dq-status"),
    toprow: document.getElementById("dq-toprow"),
    tbodyCompleteness: document.querySelector("#dq-completeness-tbl tbody"),
    detailsNote: document.getElementById("dq-details-note"),
  };

  function metric(lbl, val, sub, kind) {
    return `<div class="dq-metric ${kind || ""}"><div class="lbl">${lbl}</div><div class="val">${val}</div><div class="sub">${sub}</div></div>`;
  }

  fetch("/api/v1/data-quality/summary/")
    .then(r => r.json())
    .then(s => {
      els.status.textContent = `Inspected ${s.records_total.toLocaleString()} records. Numbers below are computed live from the database.`;
      els.toprow.innerHTML = [
        metric("Records total", s.records_total.toLocaleString(), "post-ETL, pre-QA"),
        metric("Geocoded", s.geocoded.pct + "%", `${s.geocoded.count.toLocaleString()} of ${s.records_total.toLocaleString()}`, s.geocoded.pct >= 85 ? "" : "warn"),
        metric("Region matched", s.region_matched.pct + "%", `${s.region_matched.count.toLocaleString()} of ${s.records_total.toLocaleString()}`),
        metric("District matched", s.district_matched.pct + "%", `${s.district_matched.count.toLocaleString()} of ${s.records_total.toLocaleString()}`, s.district_matched.pct >= 75 ? "" : "warn"),
        metric("Ward matched", s.ward_matched.pct + "%", `${s.ward_matched.count.toLocaleString()} of ${s.records_total.toLocaleString()}`, s.ward_matched.pct >= 75 ? "" : "warn"),
        metric("With phone", s.with_phone.pct + "%", `${s.with_phone.count.toLocaleString()} of ${s.records_total.toLocaleString()}`, s.with_phone.pct >= 50 ? "" : "bad"),
      ].join("");
    })
    .catch(err => { els.status.textContent = "Failed to load summary: " + err.message; });

  fetch("/api/v1/data-quality/details/")
    .then(r => {
      if (r.status === 403) throw new Error("restricted to Data Team accounts");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then(d => {
      els.detailsNote.textContent = `${d.likely_duplicates.toLocaleString()} likely duplicate outlets (same name + coordinates); ${d.region_mismatches.toLocaleString()} outlets where the GPS-derived region disagrees with the submitted region.`;
      els.tbodyCompleteness.innerHTML = d.field_completeness.map(f => `
        <tr>
          <td><strong>${f.label}</strong> <span style="color:#94a3b8;font-size:.72rem;">${f.field}</span></td>
          <td class="num">${f.filled.toLocaleString()}</td>
          <td class="num" style="color:${f.missing ? "#d97706" : "#94a3b8"};">${f.missing.toLocaleString()}</td>
          <td class="pct">${f.pct.toFixed(1)}%</td>
        </tr>`).join("");

      new Chart(document.getElementById("chart-completeness"), {
        type: "bar",
        data: {
          labels: d.field_completeness.map(f => f.label),
          datasets: [{ data: d.field_completeness.map(f => f.pct), backgroundColor: d.field_completeness.map(f =>
            f.pct >= 95 ? "#0d9488" : f.pct >= 80 ? "#0891b2" : f.pct >= 50 ? "#d97706" : "#dc2626") }],
        },
        options: {
          indexAxis: "y", responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { x: { beginAtZero: true, max: 100, ticks: { callback: (v) => v + "%" } } },
        },
      });

      const gs = d.gps_source;
      new Chart(document.getElementById("chart-gps-source"), {
        type: "doughnut",
        data: {
          labels: ["Tablet GPS", "Hand-held GPS", "No coordinates"],
          datasets: [{ data: [gs.tablet, gs.hand, gs.none], backgroundColor: ["#0d9488", "#0891b2", "#dc2626"] }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } },
      });
    })
    .catch(err => {
      document.getElementById("dq-details-section").innerHTML =
        `<div class="dq-note">Detailed breakdown unavailable: ${err.message}.</div>`;
    });
})();
