import math

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from common.permissions import IsRegulatorOrAbove
from outlets.models import Outlet

from .serializers import NearestOutletsRequestSerializer, SiteCheckRequestSerializer
from .services import ors_client
from .services.nearest import haversine_km

# One ORS Matrix call covers this many nearest-by-straight-line candidates,
# regardless of how many outlets match the filter/radius, so quota use stays flat.
ORS_PREFILTER_N = 30


def _outlet_row(outlet):
    return {
        "outlet": outlet,
        "dist_km": None,
        "duration_sec": None,
        "routed": False,
    }


def _apply_routing(rows, mode, lat, lon):
    """Upgrades dist_km/duration_sec in place for the given rows via one ORS
    Matrix call. Falls back silently (rows keep their straight-line dist_km)
    if the key is missing, the request fails, or ORS can't route a point."""
    if not rows:
        return False
    try:
        mx = ors_client.matrix(
            mode, (lat, lon), [(r["outlet"].latitude, r["outlet"].longitude) for r in rows]
        )
    except ors_client.OrsError:
        return False

    routed_any = False
    for r, dist, dur in zip(rows, mx["distances"], mx["durations"]):
        if dist is not None:
            r["dist_km"] = dist
            r["duration_sec"] = dur
            r["routed"] = True
            routed_any = True
    return routed_any


def _serialize_row(r):
    o = r["outlet"]
    return {
        "addo_uid": o.addo_uid,
        "name": o.name,
        "business_type": o.business_type,
        "accreditation_source": o.accreditation_source,
        "region": o.region.name if o.region else o.region_name,
        "district": o.district.name if o.district else o.district_name,
        "ward": o.ward.name if o.ward else o.ward_name,
        "village_street": o.village_street,
        "phone": o.phone,
        "latitude": o.latitude,
        "longitude": o.longitude,
        "dist_km": round(r["dist_km"], 3) if r["dist_km"] is not None else None,
        "duration_sec": r["duration_sec"],
        "routed": r["routed"],
    }


# Verdict thresholds — density (outlets/km²) inside the search radius. Ported
# verbatim from find-facility.qmd's classify(): Kariakoo/Dar CBD scores
# "saturated" (>3/km²); typical urban wards land in "well-served"; most rural
# wards register as "under-served" or "adequate".
def _classify(density, count, nearest_km):
    if count == 0:
        nearest_txt = "not on record" if nearest_km is None else f"{nearest_km:.2f} km"
        return {
            "key": "underserved",
            "label": "Under-served",
            "headline": "No accredited outlet in this radius.",
            "body": f"The nearest existing CPP is {nearest_txt} away. This location is a strong candidate for a new accredited outlet.",
        }
    if density < 0.5:
        return {
            "key": "underserved",
            "label": "Under-served",
            "headline": "Sparse coverage nearby.",
            "body": "Density is below 0.5 outlets/km². Approving a new outlet here would improve local access.",
        }
    if density < 1.5:
        return {
            "key": "adequate",
            "label": "Adequate",
            "headline": "Coverage is adequate.",
            "body": "Density sits in the 0.5–1.5 outlets/km² band. A new outlet would neither create a gap nor a saturation; assess case-by-case.",
        }
    if density < 3.0:
        return {
            "key": "well-served",
            "label": "Well-served",
            "headline": "This area is already well-served.",
            "body": "Density is 1.5–3 outlets/km². Consider whether the applicant can justify additional local demand or should be redirected to an under-served ward.",
        }
    return {
        "key": "saturated",
        "label": "Saturated",
        "headline": "This locality is saturated.",
        "body": "Density exceeds 3 outlets/km². Recommend redirecting the applicant to an under-served ward. Use the Regions view on the CPP Registry to identify gaps.",
    }


class NearestOutletsView(APIView):
    """Public: nearest N accredited outlets to a point, with real road
    distance/time when ORS routing succeeds, straight-line otherwise."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "siting"

    def post(self, request):
        serializer = NearestOutletsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        lat, lon, mode, count = d["lat"], d["lon"], d["mode"], d["count"]

        qs = Outlet.objects.filter(has_coords=True).select_related("region", "district", "ward")
        if d.get("business_type"):
            qs = qs.filter(business_type__iexact=d["business_type"])

        rows = []
        for o in qs:
            r = _outlet_row(o)
            r["dist_km"] = haversine_km(lat, lon, o.latitude, o.longitude)
            rows.append(r)
        rows.sort(key=lambda r: r["dist_km"])

        candidates = rows[: max(count, ORS_PREFILTER_N)]
        routed = _apply_routing(candidates, mode, lat, lon)
        candidates.sort(key=lambda r: r["dist_km"])

        return Response({
            "mode": mode,
            "routed": routed,
            "results": [_serialize_row(r) for r in candidates[:count]],
        })


class SiteCheckView(APIView):
    """Regulator+: outlets within a radius of a proposed site, a density
    verdict, and the nearest outlet — road distance/time when available.
    Radius/density/verdict are always straight-line (they match the circle
    drawn on the map); only the displayed distances get the road upgrade."""

    permission_classes = [IsRegulatorOrAbove]

    def post(self, request):
        serializer = SiteCheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        lat, lon, radius_km, mode = d["lat"], d["lon"], d["radius_km"], d["mode"]

        qs = Outlet.objects.filter(has_coords=True).select_related("region", "district", "ward")
        rows = []
        for o in qs:
            r = _outlet_row(o)
            r["dist_km"] = haversine_km(lat, lon, o.latitude, o.longitude)
            rows.append(r)

        in_radius = sorted((r for r in rows if r["dist_km"] <= radius_km), key=lambda r: r["dist_km"])
        nearest = min(rows, key=lambda r: r["dist_km"]) if rows else None

        candidates = list(in_radius[:ORS_PREFILTER_N])
        if nearest is not None and nearest not in candidates:
            candidates.append(nearest)
        routed = _apply_routing(candidates, mode, lat, lon)

        area_km2 = math.pi * radius_km * radius_km
        density = len(in_radius) / area_km2
        verdict = _classify(density, len(in_radius), nearest["dist_km"] if nearest else None)

        return Response({
            "radius_km": radius_km,
            "area_km2": round(area_km2, 2),
            "count_in_radius": len(in_radius),
            "density_per_km2": round(density, 3),
            "verdict": verdict,
            "nearest": _serialize_row(nearest) if nearest else None,
            "nearby": [_serialize_row(r) for r in in_radius[:50]],
            "nearby_total": len(in_radius),
            "routed": routed,
        })
