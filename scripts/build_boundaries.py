"""Simplify Tanzania GADM admin boundaries and assign each ADDO to a polygon.

Reads:
  data-raw/../boundaries/gadm41_TZA_{1,2,3}.json
  data/tanzania/addo_standardized.csv

Writes:
  data/tanzania/boundaries/tza_regions.geojson    (per-polygon addo_count baked in)
  data/tanzania/boundaries/tza_districts.geojson
  data/tanzania/boundaries/tza_wards.geojson
  data/tanzania/addo_standardized.csv             (re-written with gid_region/district/ward columns)

Design notes:
  * Assignment is ADDO-side (each outlet is placed in at most one polygon per
    admin level) so counts conserve totals — no double counting.
  * Region matching is exact on the ETL-canonicalised region name.
  * District and ward matching is fuzzy (difflib) but strictly scoped to the
    parent polygon that already matched. This avoids cross-region collisions.
"""
import json
import re
from collections import Counter
from difflib import get_close_matches
from pathlib import Path

import pandas as pd
import topojson as tp

BOUND = Path("data/tanzania/boundaries")
ADDO_CSV = Path("data/tanzania/addo_standardized.csv")


# GADM v4.1 Tanzania stores some multi-word names without spaces (e.g.
# "DaresSalaam", "KaskaziniPemba", "MorogoroRural", "IloloMpya"). Split on
# lower->upper transitions, then correct the handful of names the regex
# can't reconstruct (Dar es Salaam has an internal lowercase "es").
_MANUAL_NAME_FIXES = {
    "Dares Salaam": "Dar es Salaam",
}


def humanize_name(s):
    if not isinstance(s, str) or not s:
        return s
    out = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return _MANUAL_NAME_FIXES.get(out, out)


def norm(s):
    if not isinstance(s, str) or not s:
        return ""
    s = humanize_name(s)
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


def build():
    addo = pd.read_csv(ADDO_CSV)

    # Load + simplify all three admin levels.
    lvls = {}
    for L, tol in [(1, 0.005), (2, 0.01), (3, 0.02)]:
        src = json.loads((BOUND / f"gadm41_TZA_{L}.json").read_text(encoding="utf-8"))
        s = simplify_to_geojson(src, tol)
        restore_props(s, src)
        lvls[L] = s

    # Build polygon lookup tables scoped by parent admin.
    l1_by_key = {}
    for f in lvls[1]["features"]:
        k = norm(f["properties"]["NAME_1"])
        l1_by_key.setdefault(k, []).append(f["properties"]["GID_1"])

    l1_gid_to_name = {f["properties"]["GID_1"]: norm(f["properties"]["NAME_1"]) for f in lvls[1]["features"]}

    l2_by_region = {}
    for f in lvls[2]["features"]:
        r = norm(f["properties"]["NAME_1"])
        d = norm(f["properties"]["NAME_2"])
        l2_by_region.setdefault(r, {}).setdefault(d, []).append(f["properties"]["GID_2"])

    l2_gid_to_name = {f["properties"]["GID_2"]: norm(f["properties"]["NAME_2"]) for f in lvls[2]["features"]}

    l3_by_district = {}
    for f in lvls[3]["features"]:
        r = norm(f["properties"]["NAME_1"])
        d = norm(f["properties"]["NAME_2"])
        w = norm(f["properties"]["NAME_3"])
        l3_by_district.setdefault((r, d), {}).setdefault(w, []).append(f["properties"]["GID_3"])

    def best(candidate, choices, cutoff):
        if not candidate:
            return None
        if candidate in choices:
            return candidate
        m = get_close_matches(candidate, list(choices), n=1, cutoff=cutoff)
        return m[0] if m else None

    # Assign each ADDO -> (gid1, gid2, gid3).
    gids1, gids2, gids3 = [], [], []
    for _, r in addo.iterrows():
        rn = norm(r.get("region"))
        dn = norm(r.get("district"))
        wn = norm(r.get("ward"))

        cands = l1_by_key.get(rn, [])
        gid1 = cands[0] if len(cands) == 1 else None

        gid2 = None
        if gid1:
            region_key = l1_gid_to_name.get(gid1, "")
            pool = l2_by_region.get(region_key, {})
            d_key = best(dn, pool.keys(), cutoff=0.72)
            if d_key and len(pool[d_key]) == 1:
                gid2 = pool[d_key][0]

        gid3 = None
        if gid1 and gid2:
            region_key = l1_gid_to_name.get(gid1, "")
            district_key = l2_gid_to_name.get(gid2, "")
            pool = l3_by_district.get((region_key, district_key), {})
            w_key = best(wn, pool.keys(), cutoff=0.75)
            if w_key and len(pool[w_key]) == 1:
                gid3 = pool[w_key][0]

        gids1.append(gid1)
        gids2.append(gid2)
        gids3.append(gid3)

    addo["gid_region"] = gids1
    addo["gid_district"] = gids2
    addo["gid_ward"] = gids3

    c1 = Counter(g for g in gids1 if g)
    c2 = Counter(g for g in gids2 if g)
    c3 = Counter(g for g in gids3 if g)

    print(f"ADDOs total: {len(addo)}")
    print(f"  region-matched   : {sum(c1.values()):5d}  ({100*sum(c1.values())/len(addo):.1f}%)")
    print(f"  district-matched : {sum(c2.values()):5d}  ({100*sum(c2.values())/len(addo):.1f}%)")
    print(f"  ward-matched     : {sum(c3.values()):5d}  ({100*sum(c3.values())/len(addo):.1f}%)")

    # Trim GeoJSON properties down to what the client needs and humanise the
    # display names so tooltips/popups read "Dar es Salaam", not "DaresSalaam".
    for f in lvls[1]["features"]:
        gid = f["properties"]["GID_1"]
        f["properties"] = {
            "gid": gid,
            "name": humanize_name(f["properties"]["NAME_1"]),
            "addo_count": int(c1.get(gid, 0)),
        }
    for f in lvls[2]["features"]:
        gid = f["properties"]["GID_2"]
        f["properties"] = {
            "gid": gid,
            "name": humanize_name(f["properties"]["NAME_2"]),
            "region": humanize_name(f["properties"]["NAME_1"]),
            "addo_count": int(c2.get(gid, 0)),
        }
    for f in lvls[3]["features"]:
        gid = f["properties"]["GID_3"]
        f["properties"] = {
            "gid": gid,
            "name": humanize_name(f["properties"]["NAME_3"]),
            "district": humanize_name(f["properties"]["NAME_2"]),
            "region": humanize_name(f["properties"]["NAME_1"]),
            "addo_count": int(c3.get(gid, 0)),
        }

    paths = {1: "tza_regions.geojson", 2: "tza_districts.geojson", 3: "tza_wards.geojson"}
    for L, name in paths.items():
        js = json.dumps(lvls[L], separators=(",", ":"))
        (BOUND / name).write_text(js, encoding="utf-8")
        print(f"wrote {name:<24s} {len(lvls[L]['features']):5d} feats | {round(len(js)/1024,1):>7} KB")

    addo.to_csv(ADDO_CSV, index=False)
    print(f"wrote {ADDO_CSV} with gid_region/gid_district/gid_ward")


if __name__ == "__main__":
    build()
