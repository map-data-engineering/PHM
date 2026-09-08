// Shared OpenRouteService helpers for Find Pharmacy and Site Check.
// Key is loaded separately from ors-key.js (window.ORS_API_KEY) so the
// secret and the logic that uses it stay in different files.
//
// Free-tier limits: 2,000 requests/day, 40/min, and a matrix call is capped
// at 3,500 routes (origins x destinations). One origin x ORS_PREFILTER_N
// destinations per search stays comfortably inside that.
window.orsMatrix = async function (profile, origin, destinations) {
  if (!window.ORS_API_KEY) throw new Error("ORS_API_KEY not set");
  const locations = [[origin[1], origin[0]]].concat(
    destinations.map((d) => [d[1], d[0]]) // ORS wants [lon, lat]
  );
  const destIdx = destinations.map((_, i) => i + 1);
  const res = await fetch(`https://api.openrouteservice.org/v2/matrix/${profile}`, {
    method: "POST",
    headers: {
      "Authorization": window.ORS_API_KEY,
      "Content-Type": "application/json; charset=utf-8",
      "Accept": "application/json",
    },
    body: JSON.stringify({
      locations,
      sources: [0],
      destinations: destIdx,
      metrics: ["distance", "duration"],
      units: "km",
    }),
  });
  if (!res.ok) throw new Error(`ORS HTTP ${res.status}`);
  const data = await res.json();
  return {
    distances: (data.distances && data.distances[0]) || [],
    durations: (data.durations && data.durations[0]) || [],
  };
};

window.formatOrsDuration = function (sec) {
  if (sec == null || !isFinite(sec)) return "";
  const m = Math.round(sec / 60);
  if (m < 1) return "<1 min";
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r ? `${h}h ${r}m` : `${h}h`;
};
