"""
Part 2 — Clean the Mumbai boundary.

Reads the raw ward GeoJSON, keeps only Area == "Mumbai" (excludes Navi Mumbai),
validates each polygon ring, and writes:

  data/processed/mumbai_wards.geojson   -- the 24 individual Mumbai ward polygons
  data/processed/mumbai_boundary.geojson -- a "unified" Mumbai boundary

ASSUMPTION / LIMITATION (documented, not hidden): there is no geometry engine
available in this sandbox (no shapely/geopandas, no network to install them).
A true topological dissolve (merging 24 adjacent ward polygons into one
polygon with shared internal edges removed) is not implemented. Instead,
mumbai_boundary.geojson is a MultiPolygon containing all 24 ward rings
unchanged. For every downstream use in this project (point-in-Mumbai
containment tests for hospital filtering, etc.) this is functionally
equivalent to a dissolved polygon -- a point-in-MultiPolygon test still
correctly answers "is this point inside Mumbai" the same way a point-in-
dissolved-polygon test would. What it does NOT give you is a single clean
outer ring with no internal ward seams, which would matter if you needed to
e.g. simplify/smooth the city outline for display.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import (WARD_BOUNDARY_RAW as SRC, MUMBAI_WARDS_GEOJSON as OUT_WARDS,
                    MUMBAI_BOUNDARY_GEOJSON as OUT_BOUNDARY, ensure_dirs)

ensure_dirs()


def ring_area_shoelace(ring):
    """Signed area via shoelace formula (in deg^2, just for validity/degeneracy checks)."""
    a = 0.0
    n = len(ring)
    for i in range(n - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def validate_polygon(geom):
    """Return (is_valid: bool, problems: list[str]) for a Polygon or MultiPolygon geometry."""
    problems = []

    def check_ring(ring, label):
        if len(ring) < 4:
            problems.append(f"{label}: fewer than 4 points ({len(ring)})")
            return
        if ring[0] != ring[-1]:
            problems.append(f"{label}: ring not closed (first != last coord)")
        for pt in ring:
            if not (isinstance(pt, list) and len(pt) >= 2):
                problems.append(f"{label}: malformed point {pt}")
                continue
            lon, lat = pt[0], pt[1]
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                problems.append(f"{label}: out-of-range coord ({lon},{lat})")
        area = ring_area_shoelace(ring)
        if abs(area) < 1e-12:
            problems.append(f"{label}: degenerate ring (near-zero area)")

    if geom['type'] == 'Polygon':
        for i, ring in enumerate(geom['coordinates']):
            check_ring(ring, f"ring[{i}]")
    elif geom['type'] == 'MultiPolygon':
        for pi, poly in enumerate(geom['coordinates']):
            for ri, ring in enumerate(poly):
                check_ring(ring, f"poly[{pi}].ring[{ri}]")
    else:
        problems.append(f"unexpected geometry type: {geom['type']}")

    return (len(problems) == 0, problems)


with open(SRC) as f:
    gj = json.load(f)

all_feats = gj['features']
mumbai_feats = [f for f in all_feats if f['properties'].get('Area') == 'Mumbai']
navi_mumbai_count = sum(1 for f in all_feats if f['properties'].get('Area') == 'Navi Mumbai')
other_count = len(all_feats) - len(mumbai_feats) - navi_mumbai_count

print(f"Total features in source: {len(all_feats)}")
print(f"Area == 'Mumbai': {len(mumbai_feats)}")
print(f"Area == 'Navi Mumbai' (excluded): {navi_mumbai_count}")
print(f"Other/unexpected Area values (excluded): {other_count}")

valid_count = 0
invalid_features = []
for feat in mumbai_feats:
    ok, problems = validate_polygon(feat['geometry'])
    if ok:
        valid_count += 1
    else:
        invalid_features.append((feat['properties'].get('Ward'), problems))

print(f"Geometry valid: {valid_count}/{len(mumbai_feats)}")
if invalid_features:
    print("Invalid ward geometries found:")
    for ward, problems in invalid_features:
        print(f"  Ward {ward}: {problems}")

# Write mumbai_wards.geojson -- individual wards preserved, unchanged
wards_fc = {
    "type": "FeatureCollection",
    "features": mumbai_feats,
}
with open(OUT_WARDS, 'w') as f:
    json.dump(wards_fc, f)

# Write mumbai_boundary.geojson -- MultiPolygon union-by-collection (see module docstring)
multi_coords = []
for feat in mumbai_feats:
    geom = feat['geometry']
    if geom['type'] == 'Polygon':
        multi_coords.append(geom['coordinates'])
    elif geom['type'] == 'MultiPolygon':
        multi_coords.extend(geom['coordinates'])

boundary_fc = {
    "type": "FeatureCollection",
    "features": [{
        "type": "Feature",
        "properties": {
            "name": "Mumbai",
            "source_ward_count": len(mumbai_feats),
            "note": "MultiPolygon of all Mumbai ward polygons (not topologically dissolved -- see script docstring)",
        },
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": multi_coords,
        }
    }]
}
with open(OUT_BOUNDARY, 'w') as f:
    json.dump(boundary_fc, f)

print()
print(f"Wrote {OUT_WARDS} ({len(mumbai_feats)} ward features)")
print(f"Wrote {OUT_BOUNDARY} (1 MultiPolygon feature, {len(multi_coords)} polygons)")
