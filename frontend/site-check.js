(function () {
  const map = L.map("sc-map", { preferCanvas: true }).setView([-6.4, 35.0], 6);
  const baseOSM = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "&copy; OpenStreetMap contributors", maxZoom: 19 });
  const baseSat = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { attribution: "&copy; Esri, Maxar, Earthstar Geographics", maxZoom: 19 });
  baseOSM.addTo(map);
  L.control.layers({ "OpenStreetMap": baseOSM, "Satellite": baseSat }, null, { position: "topleft", collapsed: true }).addTo(map);

  const nearbyLayer = L.layerGroup().addTo(map);
  let pinMarker = null;
  let radiusCircle = null;

  let currentPin = null;
  let currentRadius = 2.0;
  let recomputeSeq = 0;

  const els = {
    coords: document.getElementById("sc-coords"),
    addr: document.getElementById("sc-addr"),
    locate: document.getElementById("sc-locate"),
    clear: document.getElementById("sc-clear"),
    modeSel: document.getElementById("sc-mode"),
    radius: document.getElementById("sc-radius"),
    rval: document.getElementById("sc-rval"),
    apptype: document.getElementById("sc-apptype"),
    highpop: document.getElementById("sc-highpop"),
    exemptAddo: document.getElementById("sc-exempt-addo"),
    exemptPrevPharmacy: document.getElementById("sc-exempt-prevpharmacy"),
    exemptTarmac: document.getElementById("sc-exempt-tarmac"),
    exemptForceMajeure: document.getElementById("sc-exempt-forcemajeure"),
    exemptComplex: document.getElementById("sc-exempt-complex"),
    overall: document.getElementById("sc-overall"),
    checks: document.getElementById("sc-checks"),
    nearbyBlock: document.getElementById("sc-nearby-block"),
    nearbyMeta: document.getElementById("sc-nearby-meta"),
    nearbyTbody: document.querySelector("#sc-nearby-tbl tbody"),
  };

  const OVERALL_ICON = {
    approvable: "bi-check-circle-fill",
    not_approvable: "bi-x-circle-fill",
    needs_manual_review: "bi-exclamation-triangle-fill",
  };
  const OVERALL_LABEL = {
    approvable: "Meets siting criteria",
    not_approvable: "Does not meet siting criteria",
    needs_manual_review: "Passes automated checks, but needs manual review",
  };

  map.on("click", (e) => setPin(e.latlng.lat, e.latlng.lng));

  els.radius.addEventListener("input", () => {
    currentRadius = parseFloat(els.radius.value);
    els.rval.textContent = currentRadius.toFixed(1);
    if (currentPin) recompute();
  });
  [els.modeSel, els.apptype, els.highpop, els.exemptAddo, els.exemptPrevPharmacy,
   els.exemptTarmac, els.exemptForceMajeure, els.exemptComplex].forEach(el =>
    el.addEventListener("change", () => { if (currentPin) recompute(); })
  );

  els.coords.addEventListener("change", () => {
    const m = els.coords.value.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!m) return;
    setPin(parseFloat(m[1]), parseFloat(m[2]));
  });

  els.addr.addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    const q = els.addr.value.trim();
    if (!q) return;
    els.addr.disabled = true;
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&countrycodes=tz&limit=1&q=${encodeURIComponent(q)}`;
      const res = await fetch(url, { headers: { "Accept-Language": "en" } });
      const data = await res.json();
      if (data.length) setPin(parseFloat(data[0].lat), parseFloat(data[0].lon));
      else alert("Address not found in Tanzania. Try a nearby town, or drop the pin on the map.");
    } catch (err) {
      alert("Geocoding failed: " + err.message);
    } finally { els.addr.disabled = false; }
  });

  els.locate.addEventListener("click", () => {
    if (!navigator.geolocation) { alert("Geolocation is not supported by this browser."); return; }
    els.locate.disabled = true;
    els.locate.textContent = "Locating…";
    navigator.geolocation.getCurrentPosition(
      (pos) => { els.locate.disabled = false; els.locate.textContent = "Use my location"; setPin(pos.coords.latitude, pos.coords.longitude); },
      (err) => { els.locate.disabled = false; els.locate.textContent = "Use my location"; alert("Could not get your location: " + err.message); },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  });

  els.clear.addEventListener("click", () => {
    currentPin = null;
    if (pinMarker) { map.removeLayer(pinMarker); pinMarker = null; }
    if (radiusCircle) { map.removeLayer(radiusCircle); radiusCircle = null; }
    nearbyLayer.clearLayers();
    els.coords.value = ""; els.addr.value = "";
    els.overall.className = "sc-overall empty";
    els.overall.innerHTML = `<i class="bi bi-geo-alt"></i> Drop a pin on the map to check this location.`;
    els.checks.innerHTML = "";
    els.nearbyBlock.style.display = "none";
    map.setView([-6.4, 35.0], 6);
  });

  function setPin(lat, lon) {
    currentPin = { lat, lon };
    els.coords.value = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
    if (pinMarker) map.removeLayer(pinMarker);
    pinMarker = L.marker([lat, lon], {
      icon: L.divIcon({
        className: "sc-pin",
        html: `<div style="width:22px;height:22px;background:#0f172a;border:3px solid #fff;border-radius:50%;box-shadow:0 2px 8px rgba(0,0,0,.3);"></div>`,
        iconSize: [22, 22], iconAnchor: [11, 11],
      }),
    }).addTo(map);
    recompute();
  }

  async function recompute() {
    if (!currentPin) return;
    const { lat, lon } = currentPin;
    const R = currentRadius;
    const mode = els.modeSel.value;
    const seq = ++recomputeSeq;

    if (radiusCircle) map.removeLayer(radiusCircle);
    radiusCircle = L.circle([lat, lon], {
      radius: R * 1000, color: "#0d9488", weight: 1.5, opacity: 0.6, fillColor: "#0d9488", fillOpacity: 0.08,
    }).addTo(map);
    map.fitBounds(radiusCircle.getBounds().pad(0.25));

    els.overall.className = "sc-overall empty";
    els.overall.innerHTML = `<i class="bi bi-hourglass-split"></i> Checking…`;

    let data;
    try {
      data = await Api.post("/api/v1/site-check/", {
        lat, lon, radius_km: R, mode,
        application_type: els.apptype.value,
        high_population_area: els.highpop.checked,
        is_addo_upgrade: els.exemptAddo.checked,
        is_previously_registered_pharmacy: els.exemptPrevPharmacy.checked,
        is_double_tarmac_separated: els.exemptTarmac.checked,
        is_force_majeure_relocation: els.exemptForceMajeure.checked,
        is_building_complex: els.exemptComplex.checked,
      });
    } catch (err) {
      if (seq !== recomputeSeq) return;
      els.overall.className = "sc-overall not_approvable";
      els.overall.innerHTML = `<i class="bi bi-x-circle-fill"></i> Site check failed: ${escapeHtml(err.message)}`;
      return;
    }
    if (seq !== recomputeSeq) return;

    nearbyLayer.clearLayers();
    for (const r of data.nearby) {
      L.circleMarker([r.latitude, r.longitude], {
        radius: 6, color: "#0d9488", fillColor: "#14b8a6", fillOpacity: 0.85, weight: 1.5,
      }).bindPopup(popupHtml(r)).addTo(nearbyLayer);
    }
    if (data.nearest && data.nearest.dist_km > R) {
      const n = data.nearest;
      const nearestLabel = n.routed
        ? `${n.dist_km.toFixed(2)} km by road${n.duration_sec != null ? ` (${formatDuration(n.duration_sec)})` : ""}`
        : `${n.dist_km.toFixed(2)} km (straight-line)`;
      L.circleMarker([n.latitude, n.longitude], {
        radius: 5, color: "#64748b", fillColor: "#94a3b8", fillOpacity: 0.7, weight: 1,
      }).bindPopup(popupHtml(n) + `<br/><em>Nearest overall: ${nearestLabel}</em>`).addTo(nearbyLayer);
    }

    renderResults(data);
    renderNearby(data);
  }

  function renderResults(data) {
    els.overall.className = `sc-overall ${data.overall}`;
    els.overall.innerHTML = `<i class="bi ${OVERALL_ICON[data.overall] || "bi-question-circle-fill"}"></i> <strong>${escapeHtml(OVERALL_LABEL[data.overall] || data.overall)}</strong>`;

    els.checks.innerHTML = data.checks.map(c => `
      <div class="col-md-4">
        <div class="sc-check h-100">
          <div class="d-flex justify-content-between align-items-start gap-2">
            <div class="rule">${escapeHtml(c.rule)}</div>
            <span class="badge status-badge ${c.status}">${escapeHtml(c.status.replace("_", " "))}</span>
          </div>
          <div class="detail">${escapeHtml(c.detail)}</div>
        </div>
      </div>`).join("");
  }

  function renderNearby(data) {
    els.nearbyBlock.style.display = "block";
    const radius = data.radius_km;
    if (!data.nearby.length) {
      els.nearbyTbody.innerHTML = "";
      els.nearbyMeta.textContent = `0 within ${radius.toFixed(1)} km, nearest overall is highlighted on the map`;
      return;
    }
    els.nearbyMeta.textContent = `${data.nearby_total.toLocaleString()} within ${radius.toFixed(1)} km`;
    els.nearbyTbody.innerHTML = data.nearby.map(r => {
      const timeHtml = (r.routed && r.duration_sec != null) ? `<span class="sc-dist-time">${formatDuration(r.duration_sec)}</span>` : "";
      const noteHtml = r.routed ? "" : `<span class="sc-dist-note">straight-line</span>`;
      return `
      <tr>
        <td><strong>${escapeHtml(r.name || "—")}</strong></td>
        <td>${escapeHtml(r.business_type || "—")}</td>
        <td>${escapeHtml([r.district, r.region].filter(Boolean).join(", ") || "—")}</td>
        <td class="dist">${r.dist_km.toFixed(2)} km${timeHtml}${noteHtml}</td>
      </tr>`;
    }).join("");
    if (data.nearby_total > data.nearby.length) {
      els.nearbyTbody.insertAdjacentHTML("beforeend",
        `<tr><td colspan="4" style="text-align:center;font-style:italic;color:#64748b;padding:.75rem;">Showing ${data.nearby.length} of ${data.nearby_total.toLocaleString()}. Narrow the radius for the full list.</td></tr>`);
    }
  }

  function popupHtml(r) {
    const timeSuffix = (r.routed && r.duration_sec != null) ? ` &middot; ${formatDuration(r.duration_sec)}` : "";
    const modeSuffix = r.routed ? " by road" : " (straight-line)";
    return `<strong>${escapeHtml(r.name || "—")}</strong><br/>` +
           `${escapeHtml(r.business_type || "—")} · ${escapeHtml(r.accreditation_source || "—")}<br/>` +
           `${escapeHtml([r.ward, r.district, r.region].filter(Boolean).join(", ") || "—")}<br/>` +
           `<strong style="color:#0d9488;">${r.dist_km.toFixed(2)} km${modeSuffix}</strong>${timeSuffix} from the pin`;
  }

  function formatDuration(sec) {
    if (sec == null) return "";
    const min = Math.round(sec / 60);
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60), m = min % 60;
    return `${h}h ${m}m`;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
