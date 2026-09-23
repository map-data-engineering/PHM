"""Import public/private health facilities from a CSV, for Site Check's
distance-from-health-facility rule (Pharmacy Council siting procedures,
section 1.3).

The exact source file (e.g. Tanzania's national Health Facility Registry
export) isn't pinned down yet, so column names are guessed from common
aliases and can be overridden via flags. Tier classification also falls
back to keyword matching against the facility-type text if the source
doesn't already carry a clean tier value — review the post-import summary
(and HealthFacility list in Django Admin) for anything landing in
"unclassified", and fix those up by hand or re-run with better mappings.

Usage:
    python manage.py import_health_facilities path/to/facilities.csv
    python manage.py import_health_facilities file.csv --name-col "Facility_Name" \
        --type-col "Facility_Type" --ownership-col Ownership \
        --lat-col Lat --lon-col Long --region-col Region --district-col Council
"""
import csv

from django.core.management.base import BaseCommand, CommandError

from facilities.models import HealthFacility

NAME_ALIASES = ["name", "facility_name", "facility", "hf_name"]
TYPE_ALIASES = ["tier", "level", "facility_type", "type", "hf_level", "facility_level"]
OWNERSHIP_ALIASES = ["ownership", "owner", "owner_type"]
LAT_ALIASES = ["latitude", "lat", "y"]
LON_ALIASES = ["longitude", "lon", "lng", "long", "x"]
REGION_ALIASES = ["region", "region_name"]
DISTRICT_ALIASES = ["district", "council", "district_name"]

# Keyword -> tier, checked in order (first match wins) against the
# lower-cased facility-type text when the source has no clean tier value.
TIER_KEYWORDS = [
    # Order matters: "regional referral" must be checked before the generic
    # "referral"/"national" tertiary keywords, since "Regional Referral
    # Hospital" would otherwise also match a bare "referral hospital" check.
    (("regional referral", "regional hospital"), HealthFacility.Tier.REGIONAL),
    (("zonal", "national hospital", "national referral", "tertiary"), HealthFacility.Tier.TERTIARY),
    (("district hospital", "district"), HealthFacility.Tier.DISTRICT),
    (("health centre", "health center", " hc"), HealthFacility.Tier.HEALTH_CENTRE),
    (("dispensary",), HealthFacility.Tier.DISPENSARY),
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


def _classify(text, keyword_map, default):
    low = (text or "").lower()
    for keywords, value in keyword_map:
        if any(k in low for k in keywords):
            return value
    return default


class Command(BaseCommand):
    help = "Import health facilities (hospitals/health centres/dispensaries) from a CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--name-col", default=None)
        parser.add_argument("--type-col", default=None)
        parser.add_argument("--ownership-col", default=None)
        parser.add_argument("--lat-col", default=None)
        parser.add_argument("--lon-col", default=None)
        parser.add_argument("--region-col", default=None)
        parser.add_argument("--district-col", default=None)
        parser.add_argument(
            "--replace", action="store_true",
            help="Delete all existing HealthFacility rows before importing.",
        )

    def handle(self, *args, **opts):
        with open(opts["csv_path"], newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            name_col = _find_col(header, NAME_ALIASES, opts["name_col"])
            type_col = _find_col(header, TYPE_ALIASES, opts["type_col"])
            own_col = _find_col(header, OWNERSHIP_ALIASES, opts["ownership_col"])
            lat_col = _find_col(header, LAT_ALIASES, opts["lat_col"])
            lon_col = _find_col(header, LON_ALIASES, opts["lon_col"])
            region_col = _find_col(header, REGION_ALIASES, opts["region_col"])
            district_col = _find_col(header, DISTRICT_ALIASES, opts["district_col"])

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
        skipped = 0
        created = 0

        for row in rows:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except (TypeError, ValueError):
                skipped += 1
                continue

            type_text = row.get(type_col, "") if type_col else ""
            tier = _classify(type_text, TIER_KEYWORDS, None)
            if tier is None:
                skipped += 1
                continue

            ownership_text = row.get(own_col, "") if own_col else ""
            ownership = _classify(ownership_text, OWNERSHIP_KEYWORDS, HealthFacility.Ownership.UNKNOWN)

            HealthFacility.objects.create(
                name=(row.get(name_col) or "").strip(),
                tier=tier,
                ownership=ownership,
                latitude=lat,
                longitude=lon,
                region_name=(row.get(region_col) or "").strip() if region_col else "",
                district_name=(row.get(district_col) or "").strip() if district_col else "",
                source=opts["csv_path"],
            )
            tier_counts[tier] += 1
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Imported {created} facilities, skipped {skipped} (bad coordinates or unrecognized type)."
        ))
        for tier, count in tier_counts.items():
            self.stdout.write(f"  {tier}: {count}")
        if skipped:
            self.stdout.write(self.style.WARNING(
                "Skipped rows are not in the database — review the source file's "
                "type/coordinate columns, or pass --type-col to point at the right one."
            ))
