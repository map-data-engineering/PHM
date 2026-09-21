"""Import ADDO outlets from the raw Pharmacy Council .xls inventory.

Python port of scripts/addo_etl.R (the raw .xls -> standardized-fields step)
fused with the outlet-side of scripts/build_boundaries.py (the
region/district/ward join), with one accuracy improvement over both:

  Old pipeline : outlet -> region/district/ward assigned purely by
                 name-fuzzy-matching the submitted text fields, scoped by
                 parent (~60% district/ward match rate).
  New pipeline : outlet -> if geocoded, point-in-polygon against the actual
                 Ward/District/Region boundaries first (exact); only the
                 remainder (ungeocoded rows, or points that miss every
                 polygon — simplification gaps, bad GPS) fall back to the
                 same name-fuzzy-match as before.

Also fixes the addo_uid stability bug: the R script minted
`TZ-ADDO-%05d` from row position, so a reordered re-export silently
duplicated every outlet. Here addo_uid is a hash of stable content
(name + as-submitted region/district/ward + village + rounded coordinates),
so re-running this command against an updated export **updates** existing
rows instead of duplicating them.

Usage:
    python manage.py import_outlets
    python manage.py import_outlets --source /path/to/ADDO_Inventory_Form_results-Edited.xls
"""
import hashlib
import re
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from rapidfuzz.distance import Levenshtein
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from geo.models import District, Region, Ward
from outlets.models import ImportBatch, Outlet

COLUMNS = [
    "sn", "addo_name_raw", "business_type_raw", "accreditation_source_raw",
    "po_box", "region_raw", "district_raw", "ward_raw", "village_street_raw",
    "phone_raw", "training_center_raw",
    "lat_tablet", "lon_tablet", "alt_tablet", "acc_tablet",
    "lat_hand", "lon_hand", "acc_hand",
]

BIZ_MAP = {"RA": "Retail A", "RW": "Retail Wholesale"}
ACC_MAP = {"PC": "Pharmacy Council", "TFDA": "TFDA"}

TZ_LAT = (-12.0, -0.9)
TZ_LON = (29.3, 40.5)

TZ_REGIONS = [
    "Arusha", "Dar Es Salaam", "Dodoma", "Geita", "Iringa", "Kagera", "Katavi",
    "Kigoma", "Kilimanjaro", "Lindi", "Manyara", "Mara", "Mbeya", "Morogoro",
    "Mtwara", "Mwanza", "Njombe", "Pwani", "Rukwa", "Ruvuma", "Shinyanga",
    "Simiyu", "Singida", "Songwe", "Tabora", "Tanga",
    "Kaskazini Unguja", "Kusini Unguja", "Mjini Magharibi",
    "Kaskazini Pemba", "Kusini Pemba",
]

STRIP_SUFFIX_RE = re.compile(
    r"\s+(city|cc|mc|dc|tc|mun|cicty|municipal|municipality)\b.*$", re.IGNORECASE
)
NON_ALNUM_RE = re.compile(r"[^\w\s]")
WHITESPACE_RE = re.compile(r"\s+")


def squish(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return WHITESPACE_RE.sub(" ", str(x)).strip()


def title_case(x):
    s = squish(x)
    return s.title() if s else ""


def to_num(x):
    try:
        v = float(x)
        return v if v == v else None  # filter NaN
    except (TypeError, ValueError):
        return None


def canonical_region(raw):
    """Fuzzy-match a raw region string to the closest canonical TZ region,
    replicating the R script's adist ratio >= 0.75 cutoff exactly (rapidfuzz's
    normalized Levenshtein similarity uses the same (max_len - dist)/max_len
    formula as the R code's `1 - d / pmax(nchar(a), nchar(b))`)."""
    s = squish(raw)
    if not s:
        return "", ""
    cleaned = NON_ALNUM_RE.sub(" ", s)
    cleaned = squish(cleaned).title()
    if not cleaned:
        return "", s
    stripped = squish(STRIP_SUFFIX_RE.sub("", cleaned))
    for candidate in dict.fromkeys([stripped, cleaned]):
        if not candidate:
            continue
        if candidate in TZ_REGIONS:
            return candidate, s
        best_name, best_score = None, 0.0
        for region_name in TZ_REGIONS:
            score = Levenshtein.normalized_similarity(candidate, region_name)
            if score > best_score:
                best_name, best_score = region_name, score
        if best_name and best_score >= 0.75:
            return best_name, s
    return "", s


def norm(s):
    """Normalize a name for fuzzy/exact lookup — mirrors build_boundaries.py's norm()."""
    if not s:
        return ""
    s = NON_ALNUM_RE.sub(" ", s)
    s = WHITESPACE_RE.sub(" ", s).strip().casefold()
    s = re.sub(
        r"\s+(city|cc|mc|dc|tc|mun|municipal|municipality|urban|rural|town)\b.*$", "", s
    )
    return s.strip()


def best_match(candidate, choices, cutoff):
    if not candidate:
        return None
    if candidate in choices:
        return candidate
    best_name, best_score = None, 0.0
    for choice in choices:
        score = Levenshtein.normalized_similarity(candidate, choice)
        if score > best_score:
            best_name, best_score = choice, score
    return best_name if best_score >= cutoff else None


class Command(BaseCommand):
    help = "Import ADDO outlets from the raw .xls inventory and join them to boundaries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default=str(
                settings.BASE_DIR.parent
                / "data-raw"
                / "ADDO_Inventory_Form_results-Edited.xls"
            ),
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        batch = ImportBatch.objects.create(source=source.name)
        warnings = []

        try:
            df = pd.read_excel(source, sheet_name=0, skiprows=5, header=None)
            df = df.iloc[:, : len(COLUMNS)]
            df.columns = COLUMNS[: df.shape[1]]
            df = df[df["addo_name_raw"].notna()]

            rows = [self._standardize(r) for _, r in df.iterrows()]

            with transaction.atomic():
                self._dedupe_uids(rows, warnings)
                geocoded = sum(1 for r in rows if r["has_coords"])
                self._upsert_outlets(rows, batch)
                region_matched, district_matched, ward_matched = self._join_boundaries(
                    rows, warnings
                )

            batch.row_count = len(rows)
            batch.geocoded_count = geocoded
            batch.region_matched_count = region_matched
            batch.district_matched_count = district_matched
            batch.ward_matched_count = ward_matched
            batch.warnings = warnings
            batch.status = ImportBatch.Status.SUCCESS
            batch.finished_at = timezone.now()
            batch.save()

        except Exception:
            batch.status = ImportBatch.Status.FAILED
            batch.finished_at = timezone.now()
            batch.warnings = warnings
            batch.save()
            raise

        self.stdout.write(self.style.SUCCESS(
            f"imported {batch.row_count} outlets | geocoded {batch.geocoded_count} "
            f"({100 * batch.geocoded_count / max(batch.row_count, 1):.1f}%) | "
            f"region-matched {batch.region_matched_count} | "
            f"district-matched {batch.district_matched_count} | "
            f"ward-matched {batch.ward_matched_count}"
        ))
        if warnings:
            self.stdout.write(self.style.WARNING(f"{len(warnings)} warning(s) — see ImportBatch.warnings"))

    # ── row standardization (ports addo_etl.R) ──────────────────────────
    def _standardize(self, r):
        name = squish(r.get("addo_name_raw"))
        business_type = BIZ_MAP.get(squish(r.get("business_type_raw")).upper(), "")
        accreditation_source = ACC_MAP.get(squish(r.get("accreditation_source_raw")).upper(), "")
        region, region_raw_clean = canonical_region(r.get("region_raw"))
        district_name = title_case(r.get("district_raw"))
        ward_name = title_case(r.get("ward_raw"))
        village_street = title_case(r.get("village_street_raw"))

        lat_t, lon_t, alt_t, acc_t = (
            to_num(r.get("lat_tablet")), to_num(r.get("lon_tablet")),
            to_num(r.get("alt_tablet")), to_num(r.get("acc_tablet")),
        )
        lat_h, lon_h, acc_h = (
            to_num(r.get("lat_hand")), to_num(r.get("lon_hand")), to_num(r.get("acc_hand")),
        )
        tablet_ok = lat_t is not None and lon_t is not None and TZ_LAT[0] <= lat_t <= TZ_LAT[1] and TZ_LON[0] <= lon_t <= TZ_LON[1]
        hand_ok = lat_h is not None and lon_h is not None and TZ_LAT[0] <= lat_h <= TZ_LAT[1] and TZ_LON[0] <= lon_h <= TZ_LON[1]

        if tablet_ok:
            latitude, longitude, altitude, gps_source, gps_accuracy = lat_t, lon_t, alt_t, "tablet", acc_t
        elif hand_ok:
            latitude, longitude, altitude, gps_source, gps_accuracy = lat_h, lon_h, None, "hand", acc_h
        else:
            latitude = longitude = altitude = gps_accuracy = None
            gps_source = ""

        return {
            "name": name,
            "business_type": business_type,
            "accreditation_source": accreditation_source,
            "po_box": squish(r.get("po_box")),
            "region_name": region,
            "region_raw_clean": region_raw_clean,
            "district_name": district_name,
            "ward_name": ward_name,
            "village_street": village_street,
            "phone": squish(r.get("phone_raw")),
            "training_center": squish(r.get("training_center_raw")),
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
            "gps_source": gps_source,
            "gps_accuracy": gps_accuracy,
            "has_coords": latitude is not None and longitude is not None,
        }

    # ── stable content-hash uid (fixes the positional addo_uid bug) ─────
    def _dedupe_uids(self, rows, warnings):
        seen = {}
        for r in rows:
            key = "|".join([
                r["name"].casefold(),
                r["region_name"].casefold(),
                r["district_name"].casefold(),
                r["ward_name"].casefold(),
                f"{r['latitude']:.6f}" if r["latitude"] is not None else "",
                f"{r['longitude']:.6f}" if r["longitude"] is not None else "",
            ])
            digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10].upper()
            uid = f"TZ-ADDO-{digest}"
            if uid in seen:
                seen[uid] += 1
                warnings.append(
                    f"duplicate content-hash for {r['name']!r} — disambiguated as {uid}-{seen[uid]}"
                )
                uid = f"{uid}-{seen[uid]}"
            else:
                seen[uid] = 0
            r["addo_uid"] = uid

    def _upsert_outlets(self, rows, batch):
        for r in rows:
            Outlet.objects.update_or_create(
                addo_uid=r["addo_uid"],
                defaults={
                    "name": r["name"],
                    "business_type": r["business_type"],
                    "accreditation_source": r["accreditation_source"],
                    "po_box": r["po_box"],
                    "phone": r["phone"],
                    "training_center": r["training_center"],
                    "village_street": r["village_street"],
                    "region_name": r["region_name"],
                    "district_name": r["district_name"],
                    "ward_name": r["ward_name"],
                    "region_raw_clean": r["region_raw_clean"],
                    "latitude": r["latitude"],
                    "longitude": r["longitude"],
                    "altitude": r["altitude"],
                    "gps_source": r["gps_source"],
                    "gps_accuracy": r["gps_accuracy"],
                    "has_coords": r["has_coords"],
                    "import_batch": batch,
                    # region/district/ward FKs are set by _join_boundaries below.
                },
            )

    # ── the join: point-in-polygon first, name-fuzzy-match fallback ────
    def _join_boundaries(self, rows, warnings):
        wards = list(Ward.objects.select_related("district", "district__region"))
        ward_geoms = [shape(w.geometry) for w in wards]
        ward_tree = STRtree(ward_geoms) if ward_geoms else None

        # Name-indexed lookup tables for the fallback path, scoped by parent
        # (same structure as build_boundaries.py's l1_by_key/l2_by_parent/l3_by_parent).
        regions = list(Region.objects.all())
        districts = list(District.objects.select_related("region"))

        region_by_key = {}
        for reg in regions:
            region_by_key.setdefault(norm(reg.name), []).append(reg)

        district_by_parent = {}
        for d in districts:
            district_by_parent.setdefault(norm(d.region.name), {}).setdefault(norm(d.name), []).append(d)

        ward_by_parent = {}
        for w in wards:
            region_key = norm(w.district.region.name)
            district_key = norm(w.district.name)
            ward_by_parent.setdefault((region_key, district_key), {}).setdefault(norm(w.name), []).append(w)

        region_matched = district_matched = ward_matched = 0

        for r in rows:
            region_obj = district_obj = ward_obj = None

            if r["has_coords"] and ward_tree is not None:
                pt = Point(r["longitude"], r["latitude"])
                idxs = ward_tree.query(pt)
                for i in idxs:
                    if ward_geoms[i].contains(pt):
                        ward_obj = wards[i]
                        district_obj = ward_obj.district
                        region_obj = district_obj.region
                        break

            if region_obj is None:
                cands = region_by_key.get(norm(r["region_name"]), [])
                if len(cands) == 1:
                    region_obj = cands[0]

            if district_obj is None and region_obj is not None:
                pool = district_by_parent.get(norm(region_obj.name), {})
                key = best_match(norm(r["district_name"]), pool.keys(), cutoff=0.72)
                if key and len(pool[key]) == 1:
                    district_obj = pool[key][0]

            if ward_obj is None and region_obj is not None and district_obj is not None:
                pool = ward_by_parent.get((norm(region_obj.name), norm(district_obj.name)), {})
                key = best_match(norm(r["ward_name"]), pool.keys(), cutoff=0.75)
                if key and len(pool[key]) == 1:
                    ward_obj = pool[key][0]

            if region_obj:
                region_matched += 1
            if district_obj:
                district_matched += 1
            if ward_obj:
                ward_matched += 1

            Outlet.objects.filter(addo_uid=r["addo_uid"]).update(
                region=region_obj, district=district_obj, ward=ward_obj
            )

        return region_matched, district_matched, ward_matched
