"""Import Tanzania admin boundaries (region/district/ward) into the geo app.

Port of scripts/build_boundaries.py's boundary-loading half: simplifies the
geoBoundaries NBS-derived polygons and computes parent linkage via
centroid-in-polygon lookup, then upserts Region/District/Ward rows keyed by
their stable shapeID (`gid`), so re-running this command is safe.

The outlet-to-boundary join itself now lives in
`outlets.management.commands.import_outlets` (point-in-polygon against these
polygons, falling back to name matching) — this command only builds the
boundary hierarchy.

Usage:
    python manage.py import_boundaries
    python manage.py import_boundaries --source-dir /path/to/data/tanzania/boundaries/nbs
"""
import json
from pathlib import Path

import topojson as tp
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from shapely.geometry import shape
from shapely.strtree import STRtree

from geo.models import District, Region, Ward

TOLERANCES = {1: 0.005, 2: 0.01, 3: 0.02}


def simplify_to_geojson(gj, tolerance):
    topo = tp.Topology(gj, prequantize=False)
    return json.loads(topo.toposimplify(tolerance).to_geojson())


def restore_props(simplified, original):
    for out_f, in_f in zip(simplified["features"], original["features"]):
        out_f["properties"] = in_f["properties"]


def compute_parent_shape_ids(child_features, parent_features):
    """For each child polygon, the shapeID of the parent polygon whose
    footprint contains the child's centroid (STRtree-accelerated), falling
    back to nearest-centroid when no polygon strictly contains it."""
    parent_geoms = [shape(f["geometry"]) for f in parent_features]
    parent_ids = [f["properties"]["shapeID"] for f in parent_features]
    tree = STRtree(parent_geoms)

    child_parent = []
    for cf in child_features:
        c = shape(cf["geometry"]).representative_point()
        idxs = tree.query(c)
        winner = None
        for i in idxs:
            if parent_geoms[i].contains(c):
                winner = parent_ids[i]
                break
        if winner is None and len(idxs):
            winner = parent_ids[min(idxs, key=lambda i: parent_geoms[i].distance(c))]
        child_parent.append(winner)
    return child_parent


class Command(BaseCommand):
    help = "Import/refresh the Region, District and Ward boundary hierarchy."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir",
            default=str(settings.BASE_DIR.parent / "data" / "tanzania" / "boundaries" / "nbs"),
            help="Directory containing geoboundaries_TZA_1/2/3.geojson",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source_dir"])

        raw = {}
        simplified = {}
        for level in (1, 2, 3):
            path = source_dir / f"geoboundaries_TZA_{level}.geojson"
            src = json.loads(path.read_text(encoding="utf-8"))
            raw[level] = src
            s = simplify_to_geojson(src, TOLERANCES[level])
            restore_props(s, src)
            simplified[level] = s
            self.stdout.write(f"loaded {path.name}: {len(src['features'])} features")

        self.stdout.write("computing L2 -> L1 parent linkage...")
        l2_parent = compute_parent_shape_ids(raw[2]["features"], raw[1]["features"])
        self.stdout.write("computing L3 -> L2 parent linkage...")
        l3_parent = compute_parent_shape_ids(raw[3]["features"], raw[2]["features"])

        with transaction.atomic():
            region_count = self._upsert_regions(simplified[1])
            district_count = self._upsert_districts(simplified[2], l2_parent)
            ward_count = self._upsert_wards(simplified[3], l3_parent)

        self.stdout.write(self.style.SUCCESS(
            f"regions={region_count} districts={district_count} wards={ward_count}"
        ))

    def _upsert_regions(self, features):
        count = 0
        for f in features["features"]:
            gid = f["properties"]["shapeID"]
            Region.objects.update_or_create(
                gid=gid,
                defaults={"name": f["properties"]["shapeName"], "geometry": f["geometry"]},
            )
            count += 1
        return count

    def _upsert_districts(self, features, l2_parent):
        count = 0
        for i, f in enumerate(features["features"]):
            gid = f["properties"]["shapeID"]
            parent_gid = l2_parent[i]
            region = Region.objects.filter(gid=parent_gid).first() if parent_gid else None
            if region is None:
                self.stderr.write(self.style.WARNING(
                    f"district {f['properties']['shapeName']!r} ({gid}) has no matching region — skipped"
                ))
                continue
            District.objects.update_or_create(
                gid=gid,
                defaults={
                    "name": f["properties"]["shapeName"],
                    "region": region,
                    "geometry": f["geometry"],
                },
            )
            count += 1
        return count

    def _upsert_wards(self, features, l3_parent):
        count = 0
        for i, f in enumerate(features["features"]):
            gid = f["properties"]["shapeID"]
            parent_gid = l3_parent[i]
            district = District.objects.filter(gid=parent_gid).first() if parent_gid else None
            if district is None:
                self.stderr.write(self.style.WARNING(
                    f"ward {f['properties']['shapeName']!r} ({gid}) has no matching district — skipped"
                ))
                continue
            Ward.objects.update_or_create(
                gid=gid,
                defaults={
                    "name": f["properties"]["shapeName"],
                    "district": district,
                    "geometry": f["geometry"],
                },
            )
            count += 1
        return count
