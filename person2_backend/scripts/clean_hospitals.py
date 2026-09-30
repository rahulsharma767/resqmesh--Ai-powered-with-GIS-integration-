"""
Part 3 — Clean the hospital data.

Reads the nationwide hospital_directory.csv, filters to Mumbai, validates
coordinates with a real point-in-polygon test against the Mumbai ward
boundary (data/processed/mumbai_boundary.geojson from Part 2) -- not just a
bounding box and not just trusting the word "Mumbai" in a field.

Writes:
  data/processed/mumbai_hospitals.csv         -- cleaned Mumbai hospital dataset
  data/processed/mumbai_hospitals_report.txt  -- validation/report file

Policy decisions (documented, not hidden):
  - Mumbai membership is decided by the CSV's own `District == "Mumbai"`
    field (verified in Part 1 inspection: exactly one clean value, no
    "Mumbai Suburban"/variant merge needed). This is the authoritative
    administrative filter per the task's real dataset.
  - Geographic point-in-polygon testing is used as a SECONDARY validation
    layer to catch bad/mis-entered coordinates (Part 1 found ~21 Mumbai-
    labeled rows whose coordinates land in Gujarat/Rajasthan/South Carolina,
    etc.) -- not to redefine what counts as Mumbai.
  - `usable_for_routing` is True only if: coordinates parse AND point falls
    inside the real Mumbai ward polygon boundary (exact ray-casting test,
    not a buffer/approximation). Hospitals failing this are KEPT in the
    output (never silently dropped) but flagged unusable.
  - Fields recorded as "0" or blank in the source are treated as "not
    provided" (missing), not as a literal zero value, for Emergency_Services /
    Total_Num_Beds / Specialties / Facilities.
  - Exact duplicates (same normalized name + same coordinates) are dropped,
    keeping the first occurrence. Rows sharing only a name (possibly
    different branches/addresses) are KEPT, not deduplicated, since dropping
    them without an address/coordinate check would be guessing.
"""
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import (HOSPITAL_CSV_RAW as HOSPITALS_SRC, MUMBAI_BOUNDARY_GEOJSON as BOUNDARY_SRC,
                    MUMBAI_HOSPITALS_CSV as OUT_CSV, MUMBAI_HOSPITALS_REPORT as OUT_REPORT, ensure_dirs)

ensure_dirs()


def point_in_ring(lon, lat, ring):
    """Ray-casting point-in-polygon test for one ring."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def point_in_polygon_geom(lon, lat, geom):
    """geom is a Polygon or MultiPolygon dict. Handles holes (rings after the first are holes)."""
    def in_polygon_coords(poly_coords):
        if not poly_coords:
            return False
        if not point_in_ring(lon, lat, poly_coords[0]):
            return False
        for hole in poly_coords[1:]:
            if point_in_ring(lon, lat, hole):
                return False
        return True

    if geom['type'] == 'Polygon':
        return in_polygon_coords(geom['coordinates'])
    elif geom['type'] == 'MultiPolygon':
        return any(in_polygon_coords(poly) for poly in geom['coordinates'])
    return False


def normalize_name(name):
    if not name:
        return name
    name = re.sub(r'\s+', ' ', name.strip())
    return name


def parse_coord(s):
    if not s or str(s).strip() in ('', '0'):
        return None, None
    parts = str(s).split(',')
    if len(parts) != 2:
        return None, None
    try:
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
        return lat, lon
    except ValueError:
        return None, None


def clean_field(v):
    """Treat '0'/blank as missing for attribute fields, else return stripped value."""
    if v is None:
        return ''
    v = v.strip()
    if v in ('0', ''):
        return ''
    return v


# Load Mumbai boundary
with open(BOUNDARY_SRC) as f:
    boundary_gj = json.load(f)
boundary_geom = boundary_gj['features'][0]['geometry']

# Load hospitals
with open(HOSPITALS_SRC, newline='', encoding='utf-8', errors='replace') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total_national = len(rows)
mumbai_rows = [r for r in rows if r.get('District', '').strip() == 'Mumbai']
total_mumbai = len(mumbai_rows)

# Process
seen_dedupe_keys = set()
exact_dupes_removed = 0
name_only_dupe_names = {}
missing_coord_count = 0
parseable_coord_count = 0
in_boundary_count = 0
outside_boundary_count = 0

out_rows = []
for r in mumbai_rows:
    name = normalize_name(r.get('Hospital_Name', ''))
    lat, lon = parse_coord(r.get('Location_Coordinates', ''))

    if lat is None:
        missing_coord_count += 1
        has_coords = False
        in_boundary = False
    else:
        parseable_coord_count += 1
        has_coords = True
        in_boundary = point_in_polygon_geom(lon, lat, boundary_geom)
        if in_boundary:
            in_boundary_count += 1
        else:
            outside_boundary_count += 1

    dedupe_key = (name.lower(), r.get('Location_Coordinates', '').strip())
    if has_coords and dedupe_key in seen_dedupe_keys:
        exact_dupes_removed += 1
        continue
    if has_coords:
        seen_dedupe_keys.add(dedupe_key)

    name_only_dupe_names[name.lower()] = name_only_dupe_names.get(name.lower(), 0) + 1

    usable_for_routing = has_coords and in_boundary

    out_rows.append({
        'hospital_id': clean_field(r.get('Sr_No', '')),
        'hospital_name': name,
        'lat': f'{lat:.7f}' if lat is not None else '',
        'lon': f'{lon:.7f}' if lon is not None else '',
        'has_coords': has_coords,
        'in_mumbai_boundary': in_boundary,
        'usable_for_routing': usable_for_routing,
        'category': clean_field(r.get('Hospital_Category', '')),
        'care_type': clean_field(r.get('Hospital_Care_Type', '')),
        'discipline': clean_field(r.get('Discipline_Systems_of_Medicine', '')),
        'address': clean_field(r.get('Address_Original_First_Line', '')),
        'subdistrict': clean_field(r.get('Subdistrict', '')),
        'town': clean_field(r.get('Town', '')),
        'pincode': clean_field(r.get('Pincode', '')),
        'emergency_services': clean_field(r.get('Emergency_Services', '')),
        'total_beds': clean_field(r.get('Total_Num_Beds', '')),
        'num_doctors': clean_field(r.get('Number_Doctor', '')),
        'specialties': clean_field(r.get('Specialties', '')),
        'facilities': clean_field(r.get('Facilities', '')),
        'misc_facilities': clean_field(r.get('Miscellaneous_Facilities', '')),
        'accreditation': clean_field(r.get('Accreditation', '')),
        'telephone': clean_field(r.get('Telephone', '')),
        'mobile_number': clean_field(r.get('Mobile_Number', '')),
        'emergency_num': clean_field(r.get('Emergency_Num', '')),
        'ambulance_phone': clean_field(r.get('Ambulance_Phone_No', '')),
        'bloodbank_phone': clean_field(r.get('Bloodbank_Phone_No', '')),
        'registration_number': clean_field(r.get('Hospital_Regis_Number', '')),
        'established_year': clean_field(r.get('Establised_Year', '')),
        'source': 'hospital_directory.csv',
    })

name_dupes = sum(1 for k, c in name_only_dupe_names.items() if c > 1)

# Write output CSV
if out_rows:
    fieldnames = list(out_rows[0].keys())
    with open(OUT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

# Write report
report_lines = [
    "ResQMesh -- Mumbai Hospital Data Validation Report",
    "=" * 55,
    "",
    f"Total hospital records nationwide (source file): {total_national}",
    f"Records with District == 'Mumbai': {total_mumbai}",
    f"Exact duplicates removed (same name + same coordinates): {exact_dupes_removed}",
    f"Records with a name shared by >1 row (kept, not deduped -- possibly branches): {name_dupes}",
    "",
    f"Final rows in mumbai_hospitals.csv: {len(out_rows)}",
    f"  - With parseable coordinates: {parseable_coord_count}",
    f"  - Missing/unparseable coordinates: {missing_coord_count}",
    f"  - Coordinates inside real Mumbai ward boundary (point-in-polygon): {in_boundary_count}",
    f"  - Coordinates outside Mumbai boundary despite District=='Mumbai' (likely bad data entry): {outside_boundary_count}",
    f"  - usable_for_routing = True (has coords AND inside boundary): {sum(1 for r in out_rows if r['usable_for_routing'])}",
    "",
    "Notes:",
    "  - Rows without usable coordinates are KEPT in the output (has_coords/",
    "    usable_for_routing = False) rather than deleted, per task instructions.",
    "  - '0' or blank values in Emergency_Services/Total_Num_Beds/Specialties/",
    "    Facilities are treated as 'not provided' and written as empty strings.",
    "  - Point-in-polygon test uses the real 24-ward Mumbai boundary from Part 2,",
    "    not a bounding box -- this is why some 'Mumbai' rows can still fail",
    "    in_mumbai_boundary despite being in a generally Mumbai-shaped area",
    "    (e.g. reclaimed land / boundary edge precision in the source ward file).",
]
report_text = '\n'.join(report_lines)
with open(OUT_REPORT, 'w') as f:
    f.write(report_text)

print(report_text)
