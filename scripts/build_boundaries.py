"""Simplify Tanzania NBS-derived admin boundaries and assign each CPP to a polygon.

Source (as of 2026-08):
  * L1 (regions)   — geoBoundaries gbOpen TZA ADM1 (OSM-curated, 30 features)
  * L2 (districts) — geoBoundaries gbOpen TZA ADM2, source = Tanzania NBS +
    UN OCHA ROSA (170 features)  ← the authoritative NBS layer
  * L3 (wards)     — geoBoundaries gbOpen TZA ADM3 (OSM-curated, 3,644 features)

geoBoundaries features have a flat `shapeName` property with no parent
linkage, so we compute parents spatially (each L2 centroid ↦ its L1;
each L3 centroid ↦ its L2). This gives us the region / district / ward
hierarchy needed by the choropleth.

Reads:
  data/tanzania/boundaries/nbs/geoboundaries_TZA_{1,2,3}.geojson
  data/tanzania/addo_standardized.csv

Writes:
  data/tanzania/boundaries/tza_regions.geojson    (per-polygon addo_count baked in)
  data/tanzania/boundaries/tza_districts.geojson
  data/tanzania/boundaries/tza_wards.geojson
  data/tanzania/addo_standardized.csv             (re-written with gid_region/district/ward)
"""
import json
import re
from collections import Counter
from difflib import get_close_matches
from pathlib import Path

import pandas as pd
import topojson as tp
from shapely.geometry import shape
from shapely.strtree import STRtree

BOUND_SRC = Path("data/tanzania/boundaries/nbs")
BOUND_OUT = Path("data/tanzania/boundaries")
ADDO_CSV  = Path("data/tanzania/addo_standardized.csv")


def norm(s):
    if not isinstance(s, str) or not s:
        return ""
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().casefold()
    s = re.sub(
        r"\s+(city|cc|mc|dc|tc|mun|municipal|municipality|urban|rural|town)\b.*$",
        "",
        s,
    )
    return s.strip()


def simplify_to_geojson(gj, tolerance):
    topo = tp.Topology(gj, prequantize=False)
    return json.loads(topo.toposimplify(tolerance).to_geojson())


def restore_props(simplified, original):
    for out_f, in_f in zip(simplified["features"], original["features"]):
        out_f["properties"] = in_f["properties"]


def compute_parent_shape_ids(child_features, parent_features):
    """For each child polygon, return the shapeID of the parent polygon whose
    footprint contains the child's centroid. Uses an STR tree for speed."""
    parent_geoms = [shape(f["geometry"]) for f in parent_features]
    parent_ids   = [f["properties"]["shapeID"] for f in parent_features]
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
            # Fallback: nearest neighbour by centroid distance
            winner = parent_ids[min(idxs, key=lambda i: parent_geoms[i].distance(c))]
        child_parent.append(winner)
    return child_parent


def build():
    # ── 1. Load + simplify each level ───────────────────────────────
    tolerances = {1: 0.005, 2: 0.01, 3: 0.02}
    lvls_raw = {}
    lvls = {}
    for L in (1, 2, 3):
        src = json.loads((BOUND_SRC / f"geoboundaries_TZA_{L}.geojson").read_text(encoding="utf-8"))
        lvls_raw[L] = src
        s = simplify_to_geojson(src, tolerances[L])
        restore_props(s, src)
        lvls[L] = s

    # ── 2. Derive parent linkage via centroid-in-polygon lookup ─────
    # We use the *raw* (unsimplified) parent polygons for the containment
    # test so simplification artefacts along shared boundaries don't push
    # a child's centroid outside the parent.
    print("computing L2 → L1 parent linkage…")
    l2_parent_L1 = compute_parent_shape_ids(lvls_raw[2]["features"], lvls_raw[1]["features"])
    print("computing L3 → L2 parent linkage…")
    l3_parent_L2 = compute_parent_shape_ids(lvls_raw[3]["features"], lvls_raw[2]["features"])

    # Map shapeID → (name, parent_shape_id) at each level
    l1_meta = {f["properties"]["shapeID"]: (f["properties"]["shapeName"], None)
               for f in lvls[1]["features"]}
    l2_meta = {f["properties"]["shapeID"]: (f["properties"]["shapeName"], l2_parent_L1[i])
               for i, f in enumerate(lvls[2]["features"])}
    l3_meta = {f["properties"]["shapeID"]: (f["properties"]["shapeName"], l3_parent_L2[i])
               for i, f in enumerate(lvls[3]["features"])}

    # ── 3. Load CPP data ────────────────────────────────────────────
    cpp = pd.read_csv(ADDO_CSV)

    # ── 4. Build name → shapeID lookup tables, scoped by parent ─────
    l1_by_key = {}
    for sid, (name, _) in l1_meta.items():
        l1_by_key.setdefault(norm(name), []).append(sid)

    l2_by_parent = {}
    for sid, (name, parent) in l2_meta.items():
        parent_name = norm(l1_meta[parent][0]) if parent in l1_meta else ""
        l2_by_parent.setdefault(parent_name, {}).setdefault(norm(name), []).append(sid)

    l3_by_parent = {}
    for sid, (name, parent) in l3_meta.items():
        if parent not in l2_meta:
            continue
        parent_name = norm(l2_meta[parent][0])
        grand_parent = l2_meta[parent][1]
        grand_name   = norm(l1_meta[grand_parent][0]) if grand_parent in l1_meta else ""
        l3_by_parent.setdefault((grand_name, parent_name), {}).setdefault(norm(name), []).append(sid)

    def best(candidate, choices, cutoff):
        if not candidate:
            return None
        if candidate in choices:
            return candidate
        m = get_close_matches(candidate, list(choices), n=1, cutoff=cutoff)
        return m[0] if m else None

    # ── 5. Assign each CPP → (sid1, sid2, sid3) ─────────────────────
    sids1, sids2, sids3 = [], [], []
    for _, r in cpp.iterrows():
        rn = norm(r.get("region"))
        dn = norm(r.get("district"))
        wn = norm(r.get("ward"))

        cands = l1_by_key.get(rn, [])
        sid1 = cands[0] if len(cands) == 1 else None

        sid2 = None
        if sid1:
            region_key = norm(l1_meta[sid1][0])
            pool = l2_by_parent.get(region_key, {})
            d_key = best(dn, pool.keys(), cutoff=0.72)
            if d_key and len(pool[d_key]) == 1:
                sid2 = pool[d_key][0]

        sid3 = None
        if sid1 and sid2:
            region_key   = norm(l1_meta[sid1][0])
            district_key = norm(l2_meta[sid2][0])
            pool = l3_by_parent.get((region_key, district_key), {})
            w_key = best(wn, pool.keys(), cutoff=0.75)
            if w_key and len(pool[w_key]) == 1:
                sid3 = pool[w_key][0]

        sids1.append(sid1)
        sids2.append(sid2)
        sids3.append(sid3)

    cpp["gid_region"]   = sids1
    cpp["gid_district"] = sids2
    cpp["gid_ward"]     = sids3

    c1 = Counter(g for g in sids1 if g)
    c2 = Counter(g for g in sids2 if g)
    c3 = Counter(g for g in sids3 if g)

    print(f"CPPs total: {len(cpp)}")
    print(f"  region-matched   : {sum(c1.values()):5d}  ({100*sum(c1.values())/len(cpp):.1f}%)")
    print(f"  district-matched : {sum(c2.values()):5d}  ({100*sum(c2.values())/len(cpp):.1f}%)")
    print(f"  ward-matched     : {sum(c3.values()):5d}  ({100*sum(c3.values())/len(cpp):.1f}%)")

    # ── 6. Trim + write GeoJSONs ────────────────────────────────────
    for f in lvls[1]["features"]:
        sid = f["properties"]["shapeID"]
        f["properties"] = {
            "gid": sid,
            "name": f["properties"]["shapeName"],
            "addo_count": int(c1.get(sid, 0)),
        }
    for i, f in enumerate(lvls[2]["features"]):
        sid = f["properties"]["shapeID"]
        parent_sid = l2_parent_L1[i]
        f["properties"] = {
            "gid": sid,
            "name": f["properties"]["shapeName"],
            "region": l1_meta[parent_sid][0] if parent_sid in l1_meta else "",
            "addo_count": int(c2.get(sid, 0)),
        }
    for i, f in enumerate(lvls[3]["features"]):
        sid = f["properties"]["shapeID"]
        parent_sid = l3_parent_L2[i]
        district_name = l2_meta[parent_sid][0] if parent_sid in l2_meta else ""
        grand_sid = l2_meta[parent_sid][1] if parent_sid in l2_meta else None
        region_name = l1_meta[grand_sid][0] if grand_sid in l1_meta else ""
        f["properties"] = {
            "gid": sid,
            "name": f["properties"]["shapeName"],
            "district": district_name,
            "region": region_name,
            "addo_count": int(c3.get(sid, 0)),
        }

    paths = {1: "tza_regions.geojson", 2: "tza_districts.geojson", 3: "tza_wards.geojson"}
    for L, name in paths.items():
        js = json.dumps(lvls[L], separators=(",", ":"))
        (BOUND_OUT / name).write_text(js, encoding="utf-8")
        print(f"wrote {name:<24s} {len(lvls[L]['features']):5d} feats | {round(len(js)/1024,1):>7} KB")

    cpp.to_csv(ADDO_CSV, index=False)
    print(f"wrote {ADDO_CSV} with gid_region/gid_district/gid_ward")


if __name__ == "__main__":
    build()
