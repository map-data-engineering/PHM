"""Server-side OpenRouteService Matrix client.

The API key now lives only in a Render env var, read via settings.ORS_API_KEY —
never serialized to the browser, unlike the old static site's ors-key.js.
"""
import json
import urllib.error
import urllib.request

from django.conf import settings


class OrsError(Exception):
    pass


def matrix(profile, origin, destinations, timeout=10):
    """origin: (lat, lon); destinations: [(lat, lon), ...].
    Returns {"distances": [km, ...], "durations": [sec, ...]}, aligned to destinations."""
    if not settings.ORS_API_KEY:
        raise OrsError("ORS_API_KEY not configured")
    if not destinations:
        return {"distances": [], "durations": []}

    locations = [[origin[1], origin[0]]] + [[d[1], d[0]] for d in destinations]
    body = json.dumps({
        "locations": locations,
        "sources": [0],
        "destinations": list(range(1, len(locations))),
        "metrics": ["distance", "duration"],
        "units": "km",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.openrouteservice.org/v2/matrix/{profile}",
        data=body,
        method="POST",
        headers={
            "Authorization": settings.ORS_API_KEY,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OrsError(str(exc)) from exc

    distances = (data.get("distances") or [[]])[0]
    durations = (data.get("durations") or [[]])[0]
    return {"distances": distances, "durations": durations}
