"""Data-quality metrics, computed live from the Outlet table.

Pure functions (no caching) — at ~4,900 rows this is well under 50ms and
always reflects the current data, unlike the old static site's numbers
which were frozen at whatever the CSV looked like on the last Quarto build.
"""
from django.db.models import Count

from outlets.models import Outlet

NUMERIC_FIELDS = {"latitude", "longitude", "altitude", "gps_accuracy"}

FIELDS = [
    ("addo_uid", "UID"),
    ("name", "Outlet name"),
    ("business_type", "Business type"),
    ("accreditation_source", "Accreditation"),
    ("po_box", "P.O. Box"),
    ("region_name", "Region (canonical)"),
    ("region_raw_clean", "Region (raw)"),
    ("district_name", "District"),
    ("ward_name", "Ward"),
    ("village_street", "Village / street"),
    ("phone", "Phone"),
    ("training_center", "Training centre"),
    ("latitude", "Latitude"),
    ("longitude", "Longitude"),
    ("altitude", "Altitude"),
    ("gps_source", "GPS source"),
    ("gps_accuracy", "GPS accuracy"),
]


def _pct(n, d):
    return round(1000 * n / d) / 10 if d else 0.0


def _filled_count(field):
    if field in NUMERIC_FIELDS:
        return Outlet.objects.filter(**{f"{field}__isnull": False}).count()
    return Outlet.objects.exclude(**{field: ""}).count()


def summary():
    n = Outlet.objects.count()
    geo = Outlet.objects.filter(has_coords=True).count()
    region_matched = Outlet.objects.filter(region__isnull=False).count()
    district_matched = Outlet.objects.filter(district__isnull=False).count()
    ward_matched = Outlet.objects.filter(ward__isnull=False).count()
    with_phone = _filled_count("phone")

    return {
        "records_total": n,
        "geocoded": {"count": geo, "pct": _pct(geo, n)},
        "region_matched": {"count": region_matched, "pct": _pct(region_matched, n)},
        "district_matched": {"count": district_matched, "pct": _pct(district_matched, n)},
        "ward_matched": {"count": ward_matched, "pct": _pct(ward_matched, n)},
        "with_phone": {"count": with_phone, "pct": _pct(with_phone, n)},
    }


def field_completeness():
    n = Outlet.objects.count()
    rows = []
    for field, label in FIELDS:
        filled = _filled_count(field)
        rows.append({
            "field": field, "label": label,
            "filled": filled, "missing": n - filled, "pct": _pct(filled, n),
        })
    rows.sort(key=lambda r: r["pct"])
    return rows


def gps_source_breakdown():
    out = {"tablet": 0, "hand": 0, "none": 0}
    for row in Outlet.objects.values("gps_source").annotate(n=Count("id")):
        key = row["gps_source"] or "none"
        out[key] = out.get(key, 0) + row["n"]
    return out


def likely_duplicate_count():
    """Outlets sharing the same name + coordinates — a cheap proxy for the
    near-duplicate rows the original manual data audit flagged."""
    qs = (
        Outlet.objects.filter(has_coords=True)
        .values("name", "latitude", "longitude")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    return sum(row["n"] for row in qs)


def details():
    return {
        "field_completeness": field_completeness(),
        "gps_source": gps_source_breakdown(),
        "likely_duplicates": likely_duplicate_count(),
    }
