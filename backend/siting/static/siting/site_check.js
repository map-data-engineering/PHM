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
    verdict: document.getElementById("sc-verdict"),
    nearbyBlock: document.getElementById("sc-nearby-block"),
    nearbyMeta: document.getElementById("sc-nearby-meta"),
    nearbyTbody: document.querySelector("#sc-nearby-tbl tbody"),
  };

  function getCookie(name) {
    const m = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return m ? decodeURIComponent(m[2]) : null;
  }

  map.on("click", (e) => setPin(e.latlng.lat, e.latlng.lng));

  els.radius.addEventListener("input", () => {
    currentRadius = parseFloat(els.radius.value);
    els.rval.textContent = currentRadius.toFixed(1);
    if (currentPin) recompute();
  });
  els.modeSel.addEventListener("change", () => { if (currentPin) recompute(); });

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
    els.verdict.className = "sc-verdict empty";
    els.verdict.textContent = "Drop a pin on the map to check this location.";
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

    els.verdict.className = "sc-verdict empty";
    els.verdict.textContent = "Checking…";

    let data;
    try {
      const res = await fetch("/api/v1/site-check/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") || "" },
        body: JSON.stringify({ lat, lon, radius_km: R, mode }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (err) {
      if (seq !== recomputeSeq) return;
      els.verdict.className = "sc-verdict empty";
      els.verdict.textContent = "Site check failed: " + err.message;
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

    renderVerdict(data);
    renderNearby(data);
  }

  function renderVerdict(data) {
    const v = data.verdict;
    const nearest = data.nearest;
    let nearestVal = "&mdash;";
    if (nearest) {
      nearestVal = nearest.dist_km.toFixed(2) + " km";
      nearestVal += nearest.routed
        ? (nearest.duration_sec != null ? ` <span class="sc-dist-time" style="display:inline;">(${formatDuration(nearest.duration_sec)})</span>` : "")
        : ` <span class="sc-dist-note" style="display:inline;">straight-line</span>`;
    }
    els.verdict.className = `sc-verdict ${v.key}`;
    els.verdict.innerHTML = `
      <span class="badge">${escapeHtml(v.label)}</span>
      <h3>${escapeHtml(v.headline)}</h3>
      <p>${v.body}</p>
      <div class="sc-metrics">
        <div class="sc-metric"><div class="lbl">Outlets within ${data.radius_km.toFixed(1)} km</div><div class="val">${data.count_in_radius.toLocaleString()}</div></div>
        <div class="sc-metric"><div class="lbl">Density (per km&sup2;)</div><div class="val">${data.density_per_km2.toFixed(2)}</div></div>
        <div class="sc-metric"><div class="lbl">Nearest outlet</div><div class="val">${nearestVal}</div></div>
        <div class="sc-metric"><div class="lbl">Circle area</div><div class="val">${data.area_km2.toFixed(1)} km&sup2;</div></div>
      </div>`;
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
