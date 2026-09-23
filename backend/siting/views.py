import math

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from common.permissions import IsRegulatorOrAbove
from outlets.models import Outlet

from .serializers import NearestOutletsRequestSerializer, SiteCheckRequestSerializer
from .services import facility_rules, ors_client
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
    """Regulator+: checks a proposed site against the Pharmacy Council's
    actual siting rules (distance from existing pharmacies, distance from
    public health facilities), plus a nearby-outlets list for context.
    Every rule's pass/fail is straight-line (the source document specifies
    a radius in meters, not a road distance); road distance/time is shown
    only for the informational nearest-outlet/nearby list."""

    permission_classes = [IsRegulatorOrAbove]

    def post(self, request):
        serializer = SiteCheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        lat, lon, radius_km, mode = d["lat"], d["lon"], d["radius_km"], d["mode"]

        exemptions = {
            k: d[k] for k in (
                "is_addo_upgrade", "is_previously_registered_pharmacy",
                "is_double_tarmac_separated", "is_force_majeure_relocation",
                "is_building_complex",
            )
        }
        checks = [
            facility_rules.check_pharmacy_distance(
                lat, lon, d["application_type"], exemptions, d["high_population_area"]
            ),
            facility_rules.check_health_facility_distance(lat, lon),
            facility_rules.check_laboratory_distance(lat, lon),
            facility_rules.hazard_check(),
        ]
        overall = facility_rules.overall_status(checks)

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

        return Response({
            "overall": overall,
            "checks": checks,
            "radius_km": radius_km,
            "area_km2": round(area_km2, 2),
            "count_in_radius": len(in_radius),
            "density_per_km2": round(len(in_radius) / area_km2, 3),
            "nearest": _serialize_row(nearest) if nearest else None,
            "nearby": [_serialize_row(r) for r in in_radius[:50]],
            "nearby_total": len(in_radius),
            "routed": routed,
        })
