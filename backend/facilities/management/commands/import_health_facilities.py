"""Import public/private health facilities from a CSV, for Site Check's
distance-from-health-facility (section 1.3) and standalone-laboratory
(section 1.5.2) rules.

Column names are guessed from common aliases (including the exact headers
of a "HealthScope facilities export": facility_name, facility_code,
facility_type, facility_ownership, latitude, longitude, admin1, status)
and can be overridden via flags.

Tier classification for most facility_type values is a direct mapping
(Dispensary, Health Center, Health Laboratory). "Hospital" is not
tier-differentiated in typical exports, so it gets extra logic:
  - A small explicit name list catches Tanzania's actual tertiary/zonal/
    national referral hospitals (Muhimbili, Bugando, KCMC, Mbeya Zonal,
    Benjamin Mkapa, Mirembe National, ...).
  - A public hospital whose name matches its own region (admin1) is
    treated as that region's regional referral hospital — Tanzania's
    regional hospitals are conventionally the one hospital named after
    the region itself.
  - Every other public hospital defaults to "district" tier (the most
    populous category; most of the ~230 public hospitals are district
    hospitals, not regional).
  - Private "Hospital" rows are skipped entirely — rule 1.3 only
    restricts *public* facilities, so they carry no compliance meaning.

This default-to-district fallback is an approximation, not a certainty:
a regional hospital with an idiosyncratic name (not matching its region)
will be under-classified, which understates its buffer (400m -> 300m).
Review the "regional"/"tertiary" counts the command prints against a
known list of Tanzania's ~30 regions and fix any misses by hand in Django
Admin (Facilities -> Health facilities) — the tier field is directly
editable there.

Usage:
    python manage.py import_health_facilities path/to/facilities.csv
    python manage.py import_health_facilities file.csv --name-col "Facility_Name" \
        --type-col "Facility_Type" --ownership-col Ownership \
        --lat-col Lat --lon-col Long --region-col Region
"""
import csv

from django.core.management.base import BaseCommand, CommandError

from facilities.models import HealthFacility

NAME_ALIASES = ["facility_name", "name", "facility", "hf_name"]
CODE_ALIASES = ["facility_code", "code", "hf_code"]
TYPE_ALIASES = ["facility_type", "tier", "level", "type", "hf_level", "facility_level"]
OWNERSHIP_ALIASES = ["facility_ownership", "ownership", "owner", "owner_type"]
LAT_ALIASES = ["latitude", "lat", "y"]
LON_ALIASES = ["longitude", "lon", "lng", "long", "x"]
REGION_ALIASES = ["admin1", "region", "region_name"]
DISTRICT_ALIASES = ["admin2", "district", "council", "district_name"]
STATUS_ALIASES = ["status", "facility_status"]

# Tanzania's actual tertiary/zonal/national referral hospitals — a short,
# explicit list rather than a keyword guess, since getting this wrong in
# either direction has real regulatory consequences.
TERTIARY_NAMES = [
    "muhimbili", "bugando", "kcmc", "kilimanjaro christian medical",
    "mbeya zonal", "mbeya referral", "benjamin mkapa", "mkapa hospital",
    "mirembe national", "jakaya kikwete cardiac",
]

# Armed-forces/police/prison medical facilities are government-run but sit
# outside the civilian MOH tertiary/regional/district referral hierarchy
# this rule concerns — not tracked at all, rather than mis-slotted as a
# district or regional public facility.
RESTRICTED_KEYWORDS = ("military", "police", "prison", "magereza")

TYPE_KEYWORDS = [
    (("dispensary",), HealthFacility.Tier.DISPENSARY),
    (("health centre", "health center", " hc"), HealthFacility.Tier.HEALTH_CENTRE),
    (("laboratory", " lab"), HealthFacility.Tier.LABORATORY),
]

OWNERSHIP_KEYWORDS = [
    (("government", "public", "moh", "council"), HealthFacility.Ownership.PUBLIC),
    (("private", "faith", "ngo", "parastatal", "religious"), HealthFacility.Ownership.PRIVATE),
]


def _find_col(header, aliases, override):
    if override:
        if override not in header:
            raise CommandError(f"Column {override!r} not found in CSV header: {header}")
        return override
    lower = {h.lower(): h for h in header}
    for alias in aliases:
        if alias in lower:
            return lower[alias]
    return None


def _classify_ownership(text):
    low = (text or "").lower()
    for keywords, value in OWNERSHIP_KEYWORDS:
        if any(k in low for k in keywords):
            return value
    return HealthFacility.Ownership.UNKNOWN


def _classify_tier(type_text, name, region, ownership):
    """Returns a Tier value, or None if this row isn't one we track."""
    low_type = (type_text or "").lower()

    for keywords, tier in TYPE_KEYWORDS:
        if any(k in low_type for k in keywords):
            return tier

    if "hospital" not in low_type:
        return None  # clinic, maternity home, optical, ambulance, etc. — not tracked

    if ownership != HealthFacility.Ownership.PUBLIC:
        return None  # rule 1.3 only restricts public facilities

    low_name = (name or "").lower()
    if any(k in low_name for k in RESTRICTED_KEYWORDS):
        return None

    if any(k in low_name for k in TERTIARY_NAMES):
        return HealthFacility.Tier.TERTIARY

    # Regional referral hospitals are conventionally named exactly after
    # their region (e.g. plain "Mbeya", "Songwe"), not "<Region> DC" /
    # "<Region> Municipal" / "<Region> Town Council" — those qualifiers
    # mark a district/council-run facility, not the region's one regional
    # hospital, so this must be an exact match, not a substring one.
    norm_name = "".join(ch for ch in low_name if ch.isalnum())
    norm_region = "".join(ch for ch in (region or "").lower() if ch.isalnum())
    if norm_region and norm_name == norm_region:
        return HealthFacility.Tier.REGIONAL

    return HealthFacility.Tier.DISTRICT


class Command(BaseCommand):
    help = "Import health facilities (hospitals/health centres/dispensaries/labs) from a CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--name-col", default=None)
        parser.add_argument("--code-col", default=None)
        parser.add_argument("--type-col", default=None)
        parser.add_argument("--ownership-col", default=None)
        parser.add_argument("--lat-col", default=None)
        parser.add_argument("--lon-col", default=None)
        parser.add_argument("--region-col", default=None)
        parser.add_argument("--district-col", default=None)
        parser.add_argument("--status-col", default=None)
        parser.add_argument(
            "--status-value", default="operating",
            help="Only import rows whose status column contains this (case-insensitive). "
                 "Ignored if no status column is found.",
        )
        parser.add_argument(
            "--replace", action="store_true",
            help="Delete all existing HealthFacility rows before importing.",
        )

    def handle(self, *args, **opts):
        with open(opts["csv_path"], newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            name_col = _find_col(header, NAME_ALIASES, opts["name_col"])
            code_col = _find_col(header, CODE_ALIASES, opts["code_col"])
            type_col = _find_col(header, TYPE_ALIASES, opts["type_col"])
            own_col = _find_col(header, OWNERSHIP_ALIASES, opts["ownership_col"])
            lat_col = _find_col(header, LAT_ALIASES, opts["lat_col"])
            lon_col = _find_col(header, LON_ALIASES, opts["lon_col"])
            region_col = _find_col(header, REGION_ALIASES, opts["region_col"])
            district_col = _find_col(header, DISTRICT_ALIASES, opts["district_col"])
            status_col = _find_col(header, STATUS_ALIASES, opts["status_col"])

            missing = [
                label for label, col in
                [("name", name_col), ("latitude", lat_col), ("longitude", lon_col)]
                if not col
            ]
            if missing:
                raise CommandError(
                    f"Could not find column(s) for: {', '.join(missing)}. "
                    f"CSV header was: {header}. Pass --name-col/--lat-col/--lon-col explicitly."
                )

            rows = list(reader)

        if opts["replace"]:
            deleted, _ = HealthFacility.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing facilities.")

        tier_counts = {t: 0 for t in HealthFacility.Tier.values}
        skipped_status = 0
        skipped_coords = 0
        skipped_untracked_type = 0
        created = 0
        status_wanted = opts["status_value"].lower()

        for row in rows:
            if status_col and status_wanted not in (row.get(status_col) or "").lower():
                skipped_status += 1
                continue

            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except (TypeError, ValueError):
                skipped_coords += 1
                continue

            ownership = _classify_ownership(row.get(own_col, "") if own_col else "")
            region = row.get(region_col, "") if region_col else ""
            tier = _classify_tier(
                row.get(type_col, "") if type_col else "",
                row.get(name_col, ""),
                region,
                ownership,
            )
            if tier is None:
                skipped_untracked_type += 1
                continue

            HealthFacility.objects.create(
                name=(row.get(name_col) or "").strip(),
                facility_code=(row.get(code_col) or "").strip() if code_col else "",
                tier=tier,
                ownership=ownership,
                latitude=lat,
                longitude=lon,
                region_name=(region or "").strip(),
                district_name=(row.get(district_col) or "").strip() if district_col else "",
                source=opts["csv_path"],
            )
            tier_counts[tier] += 1
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Imported {created} facilities."))
        for tier, count in tier_counts.items():
            self.stdout.write(f"  {tier}: {count}")
        self.stdout.write(
            f"Skipped: {skipped_status} (status filter), {skipped_coords} (bad coordinates), "
            f"{skipped_untracked_type} (type not tracked, e.g. clinic/maternity/private hospital)."
        )
        if tier_counts[HealthFacility.Tier.REGIONAL] or tier_counts[HealthFacility.Tier.DISTRICT]:
            self.stdout.write(self.style.WARNING(
                "Public hospitals are tier-classified by name heuristics (see this command's "
                "docstring) since most exports don't label tertiary/regional/district directly. "
                "Spot-check the 'regional' list against Tanzania's actual ~30 regional referral "
                "hospitals in Django Admin and correct any that were defaulted to 'district'."
            ))
