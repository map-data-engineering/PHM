"""Site-siting compliance checks, ported from the Pharmacy Council's
"Procedures for Approving Location of New Pharmacy Premises" (approved at
the 41st Council Meeting, made under Section 34(3-c) of the Pharmacy Act,
Cap 311). Section numbers below (1.1, 1.2, ...) refer to that document.

Every distance in the source document is a straight-line radius ("150
meters radius"), not a road distance — so these checks use haversine
throughout, independent of the ORS road-routing used elsewhere in Site
Check for the informational "how far by road" display.
"""
from facilities.models import HealthFacility
from outlets.models import Outlet

from .nearest import haversine_km

# Section 1.1.1 / 1.2.2 — minimum distance from an existing retail pharmacy.
PHARMACY_DISTANCE_M = 150
PHARMACY_DISTANCE_HIGH_POPULATION_M = 100  # Section 1.2.1/1.2.2 relaxation

# Section 1.3 — minimum distance from public health facilities, by tier.
FACILITY_DISTANCE_M = {
    HealthFacility.Tier.TERTIARY: 500,
    HealthFacility.Tier.REGIONAL: 400,
    HealthFacility.Tier.DISTRICT: 300,
    HealthFacility.Tier.HEALTH_CENTRE: 200,
    HealthFacility.Tier.DISPENSARY: 200,
}

# Section 1.5.2 — minimum distance from a standalone medical laboratory.
LAB_DISTANCE_M = 50

# Section headings, for display alongside each check's verdict.
PHARMACY_RULE_LABEL = "1.1/1.2 — Distance from existing retail pharmacies"
FACILITY_RULE_LABEL = "1.3 — Distance from public health facilities"
LAB_RULE_LABEL = "1.5.2 — Distance from standalone medical laboratories"
HAZARD_RULE_LABEL = "1.5.1 — Hazard sites (fuel fumes, sewage, etc.)"

EXEMPTION_LABELS = {
    "wholesale": "Section 1.2.3 — wholesale/warehouse applications are exempt from the pharmacy-distance rule",
    "is_addo_upgrade": "Section 1.6 — upgrading a registered ADDO/DLDB to a pharmacy is exempt from the distance rule",
    "is_previously_registered_pharmacy": "Section 1.7 — a premises previously registered as a pharmacy is exempt, provided no other application has since been granted there",
    "is_double_tarmac_separated": "Section 1.8 — separated from the nearest pharmacy by two or more tarmac roads, exempt regardless of distance",
    "is_force_majeure_relocation": "Section 1.9 — force majeure/natural calamity relocation within the same locality is exempt",
    "is_building_complex": "Section 1.10 — applications inside a shopping mall/building complex are exempt from the distance rule",
}


def check_pharmacy_distance(lat, lon, application_type, exemptions, high_population_area):
    """Returns a dict describing the section 1.1/1.2 verdict. `exemptions`
    is a dict of the boolean override flags from the request (is_addo_upgrade,
    etc.) — any true flag exempts the application from this rule entirely,
    per the matching section of the guidelines."""
    if application_type == "wholesale":
        return {
            "rule": PHARMACY_RULE_LABEL,
            "status": "exempt",
            "detail": EXEMPTION_LABELS["wholesale"],
        }

    for flag, label in EXEMPTION_LABELS.items():
        if flag != "wholesale" and exemptions.get(flag):
            return {"rule": PHARMACY_RULE_LABEL, "status": "exempt", "detail": label}

    threshold_m = PHARMACY_DISTANCE_HIGH_POPULATION_M if high_population_area else PHARMACY_DISTANCE_M
    qs = Outlet.objects.filter(has_coords=True, accreditation_source__iexact="Pharmacy Council")

    nearest = None
    nearest_km = None
    for o in qs.only("name", "latitude", "longitude", "region_name", "district_name"):
        d = haversine_km(lat, lon, o.latitude, o.longitude)
        if nearest_km is None or d < nearest_km:
            nearest_km = d
            nearest = o

    if nearest is None:
        return {
            "rule": PHARMACY_RULE_LABEL,
            "status": "pass",
            "detail": "No existing registered pharmacies on record to check against.",
            "threshold_m": threshold_m,
        }

    distance_m = nearest_km * 1000
    passed = distance_m >= threshold_m
    basis = "100m (high-population/market area)" if high_population_area else "150m (standard)"
    return {
        "rule": PHARMACY_RULE_LABEL,
        "status": "pass" if passed else "fail",
        "detail": (
            f"Nearest registered pharmacy ({nearest.name}) is {distance_m:.0f}m away; "
            f"required minimum is {basis}."
        ),
        "threshold_m": threshold_m,
        "nearest_distance_m": round(distance_m, 1),
        "nearest_name": nearest.name,
    }


def check_health_facility_distance(lat, lon):
    """Section 1.3. Returns status "unknown" (not pass/fail) when no
    HealthFacility data has been imported yet — the caller must not treat
    "unknown" as compliant."""
    qs = HealthFacility.objects.filter(
        ownership=HealthFacility.Ownership.PUBLIC, tier__in=FACILITY_DISTANCE_M.keys()
    )
    if not qs.exists():
        return {
            "rule": FACILITY_RULE_LABEL,
            "status": "unknown",
            "detail": "No public health facility dataset has been imported yet — verify manually against the regional health facility register before approving.",
        }

    violations = []
    nearest_per_tier = {}
    for f in qs.only("name", "tier", "latitude", "longitude"):
        d_m = haversine_km(lat, lon, f.latitude, f.longitude) * 1000
        cur = nearest_per_tier.get(f.tier)
        if cur is None or d_m < cur["distance_m"]:
            nearest_per_tier[f.tier] = {"name": f.name, "distance_m": d_m}

    for tier, threshold_m in FACILITY_DISTANCE_M.items():
        nearest = nearest_per_tier.get(tier)
        if nearest and nearest["distance_m"] < threshold_m:
            violations.append(
                f"{nearest['name']} ({HealthFacility.Tier(tier).label}) is "
                f"{nearest['distance_m']:.0f}m away; requires {threshold_m}m."
            )

    if violations:
        return {
            "rule": FACILITY_RULE_LABEL,
            "status": "fail",
            "detail": " ".join(violations),
        }
    return {
        "rule": FACILITY_RULE_LABEL,
        "status": "pass",
        "detail": "No public health facility violates its minimum distance.",
        "nearest_per_tier": {
            tier: {"name": v["name"], "distance_m": round(v["distance_m"], 1)}
            for tier, v in nearest_per_tier.items()
        },
    }


def check_laboratory_distance(lat, lon):
    """Section 1.5.2 — unlike section 1.3, this isn't restricted to public
    facilities; any standalone laboratory counts."""
    qs = HealthFacility.objects.filter(tier=HealthFacility.Tier.LABORATORY)
    if not qs.exists():
        return {
            "rule": LAB_RULE_LABEL,
            "status": "unknown",
            "detail": "No standalone-laboratory dataset has been imported yet — verify manually before approving.",
        }

    nearest = None
    nearest_m = None
    for f in qs.only("name", "latitude", "longitude"):
        d_m = haversine_km(lat, lon, f.latitude, f.longitude) * 1000
        if nearest_m is None or d_m < nearest_m:
            nearest_m = d_m
            nearest = f

    passed = nearest_m >= LAB_DISTANCE_M
    return {
        "rule": LAB_RULE_LABEL,
        "status": "pass" if passed else "fail",
        "detail": (
            f"Nearest standalone laboratory ({nearest.name}) is {nearest_m:.0f}m away; "
            f"required minimum is {LAB_DISTANCE_M}m."
        ),
        "nearest_distance_m": round(nearest_m, 1),
        "nearest_name": nearest.name,
    }


def hazard_check():
    """Section 1.5.1. Always "unknown" — no dataset of hazard sites (fuel
    depots, open sewage, etc.) exists or is planned; this must stay a
    manual inspection item."""
    return {
        "rule": HAZARD_RULE_LABEL,
        "status": "unknown",
        "detail": "Requires on-site inspection — no dataset of hazard sites (fuel depots, contaminants, open sewage, etc.) exists to check automatically.",
    }


def overall_status(checks):
    statuses = {c["status"] for c in checks}
    if "fail" in statuses:
        return "not_approvable"
    if "unknown" in statuses:
        return "needs_manual_review"
    return "approvable"
