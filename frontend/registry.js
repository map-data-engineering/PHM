(function () {
  const BUSINESS_TYPES = ["Retail A", "Retail Wholesale"];
  const ACCREDITATION_SOURCES = ["Pharmacy Council", "TFDA"];

  const els = {
    status: document.getElementById("reg-status"),
    summary: document.getElementById("reg-summary"),
    fRegion: document.getElementById("f-region"),
    fDistrict: document.getElementById("f-district"),
    fWard: document.getElementById("f-ward"),
    fBiz: document.getElementById("f-biz"),
    fAcc: document.getElementById("f-acc"),
    fSearch: document.getElementById("f-search"),
    ctrlRegion: document.getElementById("ctrl-region"),
    ctrlDistrict: document.getElementById("ctrl-district"),
    ctrlWard: document.getElementById("ctrl-ward"),
    viewNote: document.getElementById("reg-view-note"),
    viewPills: document.querySelectorAll("[data-view]"),
  };

  // ── Map + basemap ────────────────────────────────────────────────
  const map = L.map("reg-map", { preferCanvas: true }).setView([-6.4, 35.0], 6);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "&copy; OpenStreetMap contributors", maxZoom: 19 }).addTo(map);

  let polyLayer = null;
  map.createPane("pointsPane");
  map.getPane("pointsPane").style.zIndex = 650;
  const pointsLayer = L.layerGroup().addTo(map);
  let currentView = "region"; // region | district | ward

  const RAMP = ["#f1f5f9", "#ccfbf1", "#5eead4", "#14b8a6", "#0d9488", "#0f766e", "#134e4a"];

  const legendCtl = L.control({ position: "bottomright" });
  legendCtl.onAdd = function () { this._div = L.DomUtil.create("div", "info legend"); return this._div; };
  legendCtl.update = function (breaks, unit) {
    if (!breaks) { this._div.innerHTML = ""; return; }
    let html = `<div class="lg-title">${unit} &middot; CPPs</div>`;
    for (let i = 0; i < breaks.length - 1; i++) {
      html += `<div class="lg-row"><i style="background:${RAMP[i + 1]}"></i>${breaks[i].toLocaleString()}${i === breaks.length - 2 ? "+" : "&ndash;" + (breaks[i + 1] - 1).toLocaleString()}</div>`;
    }
    html += `<div class="lg-row"><i style="background:${RAMP[0]}"></i>0</div>`;
    this._div.innerHTML = html;
  };

  const hoverCtl = L.control({ position: "topright" });
  hoverCtl.onAdd = function () {
    this._div = L.DomUtil.create("div", "info hover-panel");
    this._div.innerHTML = '<em style="color:#94a3b8;">Hover a polygon</em>';
    return this._div;
  };
  hoverCtl.update = function (props) {
    if (!props) { this._div.innerHTML = '<em style="color:#94a3b8;">Hover a polygon</em>'; return; }
    this._div.innerHTML =
      `<div class="h-name">${escapeHtml(props.name || "—")}</div>` +
      `<div class="h-count">${(props.addo_count || 0).toLocaleString()} <span style="font-weight:400;color:#64748b;font-size:.75rem;">ADDOs</span></div>`;
  };

  let currentRows = [];
  let requestSeq = 0;
  let searchDebounce = null;
  const regionChart = { instance: null };
  const accChart = { instance: null };

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ── Init ─────────────────────────────────────────────────────────
  for (const v of BUSINESS_TYPES) els.fBiz.add(new Option(v, v));
  for (const v of ACCREDITATION_SOURCES) els.fAcc.add(new Option(v, v));
  updateFilterVisibility(currentView);

  Api.get("/api/v1/boundaries/region/").then(gj => {
    for (const f of gj.features.sort((a, b) => a.properties.name.localeCompare(b.properties.name))) {
      els.fRegion.add(new Option(f.properties.name, f.properties.name));
    }
  });

  els.fRegion.addEventListener("input", () => {
    els.fDistrict.innerHTML = '<option value="">All districts</option>';
    els.fDistrict.disabled = true;
    els.fWard.innerHTML = '<option value="">All wards</option>';
    els.fWard.disabled = true;
    if (els.fRegion.value) {
      Api.get("/api/v1/boundaries/district/", { region: els.fRegion.value }).then(gj => {
        for (const f of gj.features.sort((a, b) => a.properties.name.localeCompare(b.properties.name))) {
          els.fDistrict.add(new Option(f.properties.name, f.properties.name));
        }
        els.fDistrict.disabled = gj.features.length === 0;
      });
    }
    applyFilters();
  });
  els.fDistrict.addEventListener("input", () => {
    els.fWard.innerHTML = '<option value="">All wards</option>';
    els.fWard.disabled = true;
    if (els.fDistrict.value) {
      Api.get("/api/v1/boundaries/ward/", { district: els.fDistrict.value }).then(gj => {
        for (const f of gj.features.sort((a, b) => a.properties.name.localeCompare(b.properties.name))) {
          els.fWard.add(new Option(f.properties.name, f.properties.name));
        }
        els.fWard.disabled = gj.features.length === 0;
      });
    }
    applyFilters();
  });
  [els.fWard, els.fBiz, els.fAcc].forEach(el => el.addEventListener("input", applyFilters));
  els.fSearch.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(applyFilters, 300);
  });
  els.viewPills.forEach(btn => btn.addEventListener("click", () => setView(btn.dataset.view)));

  function updateFilterVisibility(view) {
    els.ctrlRegion.style.display = view === "region" ? "" : "none";
    els.ctrlDistrict.style.display = view === "district" ? "" : "none";
    els.ctrlWard.style.display = view === "ward" ? "" : "none";
  }

  function setView(view) {
    currentView = view;
    els.viewPills.forEach(b => b.classList.toggle("active", b.dataset.view === view));
    updateFilterVisibility(view);
    applyFilters();
  }

  function pointParams() {
    return {
      region: els.fRegion.value, district: els.fDistrict.value, ward: els.fWard.value,
      business_type: els.fBiz.value, accreditation_source: els.fAcc.value,
      search: els.fSearch.value.trim(),
    };
  }

  function boundaryParams(level) {
    const p = { business_type: els.fBiz.value, accreditation_source: els.fAcc.value, search: els.fSearch.value.trim() };
    if (level === "district") p.region = els.fRegion.value;
    if (level === "ward") p.district = els.fDistrict.value;
    return p;
  }

  async function applyFilters() {
    const seq = ++requestSeq;
    els.status.textContent = "Loading…";
    let rows, geo;
    try {
      [rows, geo] = await Promise.all([
        Api.get("/api/v1/outlets/points/", pointParams()),
        Api.get(`/api/v1/boundaries/${currentView}/`, boundaryParams(currentView)),
      ]);
    } catch (err) {
      if (seq !== requestSeq) return;
      els.status.textContent = "Failed to load registry: " + err.message;
      els.status.style.borderLeftColor = "#dc2626";
      return;
    }
    if (seq !== requestSeq) return; // a newer filter change superseded this

    currentRows = rows;
    els.status.innerHTML =
      `Loaded <strong>${rows.length.toLocaleString()}</strong> outlets. ` +
      `Toggle <em>Regions</em> / <em>Districts</em> / <em>Wards</em> above to switch the map to a choropleth of CPP counts per polygon.`;
    renderSummary(rows);
    renderChoropleth(geo, currentView);
    renderPoints(rows);
    renderCharts(rows);
  }

  function renderSummary(rows) {
    const geocoded = rows.filter(r => r.latitude != null && r.longitude != null).length;
    const regions = new Set(rows.map(r => r.region).filter(Boolean)).size;
    const districts = new Set(rows.map(r => r.district).filter(Boolean)).size;
    const card = (val, lbl) => `
      <div class="col"><div class="card card-lift reg-scard h-100 text-center"><div class="card-body py-3">
        <div class="val">${val}</div><div class="lbl">${lbl}</div>
      </div></div></div>`;
    els.summary.innerHTML =
      card(rows.length.toLocaleString(), "Outlets in view") +
      card(geocoded.toLocaleString(), `With GPS (${rows.length ? Math.round(100 * geocoded / rows.length) : 0}%)`) +
      card(regions, "Regions") +
      card(districts, "Districts");
  }

  function renderPoints(rows) {
    pointsLayer.clearLayers();
    const q = els.fSearch.value.trim();
    const CAP = 300;
    const withCoords = rows.filter(r => r.latitude != null && r.longitude != null);
    const shown = q ? withCoords.slice(0, CAP) : withCoords;
    const markers = shown.map(r => L.circleMarker([r.latitude, r.longitude], {
      pane: "pointsPane", radius: 4, weight: 1, color: "#ffffff", fillColor: "#0d9488", fillOpacity: 0.85,
    }).bindPopup(
      `<strong>${escapeHtml(r.name)}</strong><br/>` +
      `${escapeHtml(r.business_type || "—")} · ${escapeHtml(r.accreditation_source || "—")}<br/>` +
      `${escapeHtml([r.ward, r.district, r.region].filter(Boolean).join(", ") || "—")}`
    ).addTo(pointsLayer));

    if (!q) return;
    if (markers.length) {
      const bounds = L.latLngBounds(shown.map(r => [r.latitude, r.longitude]));
      map.fitBounds(bounds.pad(0.3), { maxZoom: 15 });
      if (markers.length === 1) markers[0].openPopup();
      if (withCoords.length > CAP) {
        els.viewNote.style.color = "#64748b";
        els.viewNote.textContent = `Showing the first ${CAP} of ${withCoords.length.toLocaleString()} matching outlets as pins — narrow the search to see the rest.`;
      }
    } else if (rows.length) {
      els.viewNote.style.color = "#b45309";
      els.viewNote.textContent = `${rows.length.toLocaleString()} match${rows.length === 1 ? "" : "es"} found for "${q}", but none have a GPS location on file.`;
    }
  }

  function renderChoropleth(gj, level) {
    if (polyLayer) { map.removeLayer(polyLayer); polyLayer = null; }
    map.removeControl(legendCtl); map.removeControl(hoverCtl);

    const values = gj.features.map(f => f.properties.addo_count || 0);
    const breaks = computeBreaks(values);

    polyLayer = L.geoJSON(gj, {
      style: (f) => ({
        fillColor: colorFor(f.properties.addo_count || 0, breaks),
        weight: level === "ward" ? 0.3 : 0.7, opacity: 1, color: "#ffffff", fillOpacity: 0.85,
      }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties;
        layer.on({
          mouseover: (e) => { e.target.setStyle({ weight: 2, color: "#0f172a" }); e.target.bringToFront(); hoverCtl.update(p); },
          mouseout: (e) => { polyLayer.resetStyle(e.target); hoverCtl.update(null); },
          click: (e) => {
            map.fitBounds(e.target.getBounds(), { padding: [20, 20] });
            L.popup().setLatLng(e.latlng).setContent(
              `<strong>${escapeHtml(p.name)}</strong><br/>` +
              `<strong style="color:#0d9488">${(p.addo_count || 0).toLocaleString()}</strong> CPPs`
            ).openOn(map);
          },
        });
      },
    }).addTo(map);

    legendCtl.addTo(map);
    hoverCtl.addTo(map);
    legendCtl.update(breaks, level.charAt(0).toUpperCase() + level.slice(1));

    const selName = level === "region" ? els.fRegion.value : level === "district" ? els.fDistrict.value : els.fWard.value;
    const selected = selName && gj.features.find(f => f.properties.name === selName);
    if (selected) {
      const maxZoom = level === "ward" ? 13 : level === "district" ? 11 : 9;
      map.fitBounds(L.geoJSON(selected).getBounds(), { padding: [20, 20], maxZoom });
    } else if (gj.features.length) {
      map.fitBounds(L.geoJSON(gj).getBounds(), { padding: [20, 20] });
    } else {
      map.setView([-6.4, 35.0], 6);
    }

    const matched = currentRows.filter(r => r[level]).length;
    const pct = currentRows.length ? Math.round(100 * matched / currentRows.length) : 0;
    els.viewNote.style.color = "#64748b";
    els.viewNote.textContent =
      `${matched.toLocaleString()} / ${currentRows.length.toLocaleString()} outlets placed in ${level} polygons (${pct}%). ` +
      `${(currentRows.length - matched).toLocaleString()} could not be auto-matched.`;
  }

  function computeBreaks(values) {
    const nz = values.filter(v => v > 0).sort((a, b) => a - b);
    if (nz.length === 0) return [0, 1, 2, 3, 4, 5, 6];
    const q = (p) => nz[Math.min(nz.length - 1, Math.floor(p * nz.length))];
    const raw = [1, q(0.20), q(0.40), q(0.60), q(0.80), q(0.95)];
    const out = [];
    for (const v of raw) { if (!out.length || v > out[out.length - 1]) out.push(v); }
    while (out.length < 6) out.push((out[out.length - 1] || 0) + 1);
    out.push(Infinity);
    return out;
  }
  function colorFor(count, breaks) {
    if (count <= 0) return RAMP[0];
    for (let i = 0; i < breaks.length - 1; i++) {
      if (count >= breaks[i] && count < breaks[i + 1]) return RAMP[i + 1];
    }
    return RAMP[RAMP.length - 1];
  }

  function tally(rows, k, top) {
    const counts = {};
    for (const r of rows) { const v = r[k] || "Unknown"; counts[v] = (counts[v] || 0) + 1; }
    const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return top ? entries.slice(0, top) : entries;
  }
  function renderCharts(rows) {
    const regions = tally(rows, "region", 15);
    const acc = tally(rows, "accreditation_source");

    regionChart.instance = Highcharts.chart("chart-region", {
      chart: { type: "bar", height: 300 },
      title: { text: null },
      xAxis: { categories: regions.map(e => e[0]), title: { text: null } },
      yAxis: { title: { text: null }, allowDecimals: false },
      legend: { enabled: false },
      credits: { enabled: false },
      tooltip: { pointFormat: "<b>{point.y}</b> outlets" },
      plotOptions: { series: { color: "#0d9488" } },
      series: [{ name: "Outlets", data: regions.map(e => e[1]) }],
    });

    accChart.instance = Highcharts.chart("chart-acc", {
      chart: { type: "pie", height: 300 },
      title: { text: null },
      credits: { enabled: false },
      colors: ["#0d9488", "#0f172a", "#64748b", "#f59e0b"],
      plotOptions: {
        pie: { innerSize: "60%", dataLabels: { enabled: true, format: "{point.name}: {point.percentage:.1f}%" } },
      },
      legend: { enabled: true, verticalAlign: "bottom" },
      series: [{ name: "Outlets", data: acc.map(e => ({ name: e[0], y: e[1] })) }],
    });
  }

  applyFilters();
})();
