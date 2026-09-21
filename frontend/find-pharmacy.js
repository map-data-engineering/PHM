(function () {
  const els = {
    status: document.getElementById("fp-status"),
    addr: document.getElementById("fp-addr"),
    locate: document.getElementById("fp-locate"),
    typeFilt: document.getElementById("fp-type"),
    modeSel: document.getElementById("fp-mode"),
    countSel: document.getElementById("fp-count"),
    resultsBody: document.getElementById("fp-results-body"),
    resultsMeta: document.getElementById("fp-results-meta"),
  };

  const map = L.map("fp-map", { preferCanvas: true }).setView([-6.4, 35.0], 6);
  const baseOSM = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "&copy; OpenStreetMap contributors", maxZoom: 19 });
  const baseSat = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { attribution: "&copy; Esri, Maxar, Earthstar Geographics", maxZoom: 19 });
  baseOSM.addTo(map);
  L.control.layers({ "OpenStreetMap": baseOSM, "Satellite": baseSat }, null, { position: "topleft", collapsed: true }).addTo(map);

  const backdropLayer = L.layerGroup().addTo(map);
  const resultsLayer = L.layerGroup().addTo(map);
  let userMarker = null;
  let hasLocation = false;

  function updateBackdropVisibility() {
    const shouldShow = !hasLocation && map.getZoom() < 10;
    if (shouldShow && !map.hasLayer(backdropLayer)) map.addLayer(backdropLayer);
    else if (!shouldShow && map.hasLayer(backdropLayer)) map.removeLayer(backdropLayer);
  }
  map.on("zoomend", updateBackdropVisibility);

  let currentLoc = null;
  let recomputeSeq = 0;

  Api.get("/api/v1/outlets/points/")
    .then(rows => {
      const withCoords = rows.filter(r => r.latitude != null && r.longitude != null);
      for (const r of withCoords) {
        L.circleMarker([r.latitude, r.longitude], {
          radius: 2, color: "#b91c1c", weight: 0, fillColor: "#b91c1c", fillOpacity: 0.6, interactive: false,
        }).addTo(backdropLayer);
      }
      els.status.innerHTML = `<strong>${withCoords.length.toLocaleString()}</strong> accredited outlets loaded. Search an address, use your location, or click the map.`;
    })
    .catch(err => {
      els.status.className = "fp-status error";
      els.status.textContent = "Failed to load pharmacy registry: " + err.message;
    });

  map.on("click", (e) => setLocation(e.latlng.lat, e.latlng.lng, "Dropped pin"));

  els.addr.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    const q = els.addr.value.trim();
    if (!q) return;
    els.addr.disabled = true;
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&countrycodes=tz&limit=1&q=${encodeURIComponent(q)}`;
      const res = await fetch(url, { headers: { "Accept-Language": "en" } });
      const data = await res.json();
      if (data.length) setLocation(parseFloat(data[0].lat), parseFloat(data[0].lon), data[0].display_name);
      else alert("Address not found in Tanzania. Try a nearby town or drop a pin on the map.");
    } catch (err) {
      alert("Geocoding failed: " + err.message);
    } finally { els.addr.disabled = false; }
  });

  els.locate.addEventListener("click", () => {
    if (!navigator.geolocation) { alert("Geolocation is not supported by this browser."); return; }
    els.locate.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => { els.locate.disabled = false; setLocation(pos.coords.latitude, pos.coords.longitude, "My location"); },
      (err) => { els.locate.disabled = false; alert("Could not get your location: " + err.message); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  });

  els.typeFilt.addEventListener("change", () => currentLoc && recompute());
  els.modeSel.addEventListener("change", () => currentLoc && recompute());
  els.countSel.addEventListener("change", () => currentLoc && recompute());

  function setLocation(lat, lon, label) {
    currentLoc = { lat, lon, label };
    hasLocation = true;
    updateBackdropVisibility();

    if (userMarker) map.removeLayer(userMarker);
    userMarker = L.marker([lat, lon], {
      icon: L.divIcon({
        className: "fp-user",
        html: `<div style="width:26px;height:26px;background:#0f172a;border:4px solid #fff;border-radius:50%;box-shadow:0 3px 10px rgba(0,0,0,.4),0 0 0 1px rgba(15,23,42,.15);"></div>`,
        iconSize: [26, 26], iconAnchor: [13, 13],
      }),
      title: label || "Your location",
    }).addTo(map);

    recompute();
  }

  async function recompute() {
    if (!currentLoc) return;
    const { lat, lon } = currentLoc;
    const seq = ++recomputeSeq;
    els.resultsMeta.textContent = "Searching…";

    let data;
    try {
      data = await Api.post("/api/v1/nearest-outlets/", {
        lat, lon,
        business_type: els.typeFilt.value,
        mode: els.modeSel.value,
        count: parseInt(els.countSel.value, 10),
      });
    } catch (err) {
      if (seq !== recomputeSeq) return;
      els.resultsMeta.textContent = "Search failed";
      els.resultsBody.innerHTML = `<div class="fp-empty">Could not reach the search service: ${escapeHtml(err.message)}</div>`;
      return;
    }
    if (seq !== recomputeSeq) return;

    const rows = data.results;
    resultsLayer.clearLayers();
    rows.forEach((r, i) => {
      const n = i + 1;
      const marker = L.marker([r.latitude, r.longitude], {
        icon: L.divIcon({
          className: "fp-result-pin",
          html: `<div style="width:34px;height:34px;background:#0d9488;color:#fff;border:3px solid #fff;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:monospace;font-size:.92rem;font-weight:600;box-shadow:0 3px 10px rgba(0,0,0,.35),0 0 0 1px rgba(15,23,42,.15);">${n}</div>`,
          iconSize: [34, 34], iconAnchor: [17, 17],
        }),
      }).bindPopup(popupHtml(r, n)).addTo(resultsLayer);
      marker.on("click", () => highlightResult(n));
    });

    if (rows.length) {
      const bounds = L.latLngBounds([[lat, lon], ...rows.map(r => [r.latitude, r.longitude])]);
      map.fitBounds(bounds.pad(0.2), { maxZoom: 14 });
    } else {
      map.setView([lat, lon], 12);
    }

    renderList(rows);
  }

  function highlightResult(n) {
    document.querySelectorAll(".fp-card").forEach(el => {
      el.classList.toggle("active", parseInt(el.dataset.n, 10) === n);
      if (parseInt(el.dataset.n, 10) === n) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }

  function gmapsTravelMode(orsMode) {
    if (orsMode === "foot-walking") return "walking";
    if (orsMode === "cycling-regular") return "bicycling";
    return "driving";
  }

  function renderList(rows) {
    if (!rows.length) {
      els.resultsBody.innerHTML = `<div class="fp-empty">No accredited outlets match this filter within Tanzania. Try changing the business-type filter.</div>`;
      els.resultsMeta.textContent = "0 results";
      return;
    }
    const anyRouted = rows.some(r => r.routed);
    els.resultsMeta.textContent = `${rows.length} nearest (${anyRouted ? "by road" : "straight-line"})`;
    const gmapsMode = gmapsTravelMode(els.modeSel.value);
    const cards = rows.map((r, i) => {
      const n = i + 1;
      const loc = [r.ward, r.district, r.region].filter(Boolean).join(", ");
      const gmapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${r.latitude},${r.longitude}&travelmode=${gmapsMode}`;
      const phone = cleanPhone(r.phone);
      const timeHtml = (r.routed && r.duration_sec != null) ? `<div class="fp-time">${formatDuration(r.duration_sec)}</div>` : "";
      const noteHtml = r.routed ? "" : `<div class="fp-note">straight-line</div>`;
      return `
        <div class="fp-card list-group-item list-group-item-action p-3" data-n="${n}" data-lat="${r.latitude}" data-lon="${r.longitude}">
          <div class="fp-num">${n}</div>
          <div>
            <div class="fp-name">${escapeHtml(r.name || "—")}</div>
            <div class="fp-meta"><span class="type">${escapeHtml(r.business_type || "")}</span>${escapeHtml(loc || "—")}</div>
            <div class="fp-actions">
              <a href="${gmapsUrl}" target="_blank" rel="noopener" class="btn btn-sm btn-primary">Directions</a>
              ${phone ? `<a href="tel:${phone}" class="btn btn-sm btn-outline-secondary">${escapeHtml(phone)}</a>` : ""}
            </div>
          </div>
          <div class="fp-dist">
            ${r.dist_km.toFixed(2)}<span class="sub">km</span>
            ${timeHtml}
            ${noteHtml}
          </div>
        </div>`;
    }).join("");
    els.resultsBody.innerHTML = `<div class="list-group list-group-flush">${cards}</div>`;

    document.querySelectorAll(".fp-card").forEach(el => {
      el.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        const n = parseInt(el.dataset.n, 10);
        const lat = parseFloat(el.dataset.lat);
        const lon = parseFloat(el.dataset.lon);
        highlightResult(n);
        map.setView([lat, lon], 15);
        resultsLayer.getLayers().forEach((layer, i) => { if (i + 1 === n) layer.openPopup(); });
      });
    });
  }

  function popupHtml(r, n) {
    const loc = [r.ward, r.district, r.region].filter(Boolean).join(", ");
    const gmapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${r.latitude},${r.longitude}&travelmode=${gmapsTravelMode(els.modeSel.value)}`;
    const phone = cleanPhone(r.phone);
    const distLabel = r.dist_km.toFixed(2) + " km" + (r.routed ? " by road" : " (straight-line)");
    const timeLabel = (r.routed && r.duration_sec != null) ? ` &middot; ${formatDuration(r.duration_sec)}` : "";
    return `
      <div style="min-width:200px;">
        <strong>${n}. ${escapeHtml(r.name || "—")}</strong><br/>
        <span style="font-size:.7rem;text-transform:uppercase;color:#64748b;">${escapeHtml(r.business_type || "")}</span><br/>
        <span style="font-size:.85rem;">${escapeHtml(loc || "—")}</span><br/>
        <div style="margin-top:.4rem;color:#0d9488;font-weight:600;">${distLabel}${timeLabel}</div>
        <div style="margin-top:.4rem;display:flex;gap:.35rem;">
          <a href="${gmapsUrl}" target="_blank" rel="noopener" style="background:#0d9488;color:#fff;padding:.25rem .55rem;border-radius:3px;text-decoration:none;font-size:.75rem;font-weight:500;">Directions</a>
          ${phone ? `<a href="tel:${phone}" style="border:1px solid #e2e8f0;color:#0f172a;padding:.25rem .55rem;border-radius:3px;text-decoration:none;font-size:.75rem;">${escapeHtml(phone)}</a>` : ""}
        </div>
      </div>`;
  }

  function formatDuration(sec) {
    if (sec == null) return "";
    const min = Math.round(sec / 60);
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60), m = min % 60;
    return `${h}h ${m}m`;
  }

  function cleanPhone(p) {
    if (!p) return null;
    const digits = String(p).trim().replace(/[^\d+]/g, "");
    return digits || null;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
