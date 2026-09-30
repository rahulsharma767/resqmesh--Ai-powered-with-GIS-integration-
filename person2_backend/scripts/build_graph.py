"""
Part 4: Build the routable Mumbai road graph.

Reads:
  data/cache/mumbai_bbox_nodes.csv  (node_id, lat, lon)
  data/cache/mumbai_ways.csv        (way_id, highway, name, oneway, maxspeed_raw, refs)

Writes:
  data/processed/mumbai_road_nodes.csv   -- node_id, lat, lon
  data/processed/mumbai_road_edges.csv   -- u, v, length_m, speed_kph, travel_time_min,
                                             highway, name, way_id, oneway_flag

Documented assumptions (per task spec, since real-time traffic isn't available):
  - Vehicle-routable highway classes only (see extract_ways.py ALLOWED_HIGHWAY).
    Footways/paths/cycleways/steps are excluded -- this is an ambulance/vehicle
    routing graph, not a pedestrian one.
  - oneway parsing: 'yes'/'true'/'1' => forward only edge; '-1' => reverse only
    edge; anything else (including missing) => bidirectional. Implicit
    roundabout one-way-ness (junction=roundabout without an explicit oneway
    tag) is NOT inferred -- documented limitation.
  - maxspeed parsing: numeric prefix is read as km/h; an explicit 'mph' suffix
    is converted to km/h. Non-numeric values (e.g. 'IN:urban', 'walk',
    'national') fall back to the road-class default below.
  - Default speed-by-class table (km/h) reflects congested Indian urban
    conditions, NOT free-flow/highway-code speeds:
        motorway 80, motorway_link 50, trunk 60, trunk_link 40,
        primary 40, primary_link 30, secondary 35, secondary_link 25,
        tertiary 30, tertiary_link 25, unclassified 25, residential 20,
        living_street 10, service 15
    These are placeholders explicitly designed to be replaced by real-time
    traffic data later (see PART 4 / PART 17 of the spec).
"""
import csv
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import (NODES_BBOX_CACHE as NODES_CSV, WAYS_CACHE as WAYS_CSV,
                    ROAD_NODES_CSV as OUT_NODES, ROAD_EDGES_CSV as OUT_EDGES, ensure_dirs)

ensure_dirs()

DEFAULT_SPEED_KPH = {
    'motorway': 80, 'motorway_link': 50,
    'trunk': 60, 'trunk_link': 40,
    'primary': 40, 'primary_link': 30,
    'secondary': 35, 'secondary_link': 25,
    'tertiary': 30, 'tertiary_link': 25,
    'unclassified': 25,
    'residential': 20,
    'living_street': 10,
    'service': 15,
}

ONEWAY_FORWARD = {'yes', 'true', '1'}
ONEWAY_REVERSE = {'-1', 'reverse'}


def parse_maxspeed(raw, highway_class):
    if raw:
        raw = raw.strip().lower()
        is_mph = 'mph' in raw
        digits = ''.join(c for c in raw if c.isdigit() or c == '.')
        if digits:
            try:
                val = float(digits)
                if is_mph:
                    val *= 1.60934
                return val
            except ValueError:
                pass
    return DEFAULT_SPEED_KPH.get(highway_class, 25)


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


t0 = time.time()
print("Loading node coordinates...", flush=True)
node_coord = {}
with open(NODES_CSV, encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        node_coord[int(row[0])] = (float(row[1]), float(row[2]))
print(f"Loaded {len(node_coord)} node coordinates in {time.time()-t0:.1f}s", flush=True)

t0 = time.time()
edge_count = 0
bidir_count = 0
fwd_only_count = 0
rev_only_count = 0
skipped_missing_coord = 0
used_node_ids = set()
class_length_m = {}

with open(WAYS_CSV, encoding='utf-8') as f, open(OUT_EDGES, 'w', newline='', encoding='utf-8') as fout:
    reader = csv.reader(f)
    header = next(reader)
    writer = csv.writer(fout)
    writer.writerow(['u', 'v', 'length_m', 'speed_kph', 'travel_time_min', 'highway', 'name', 'way_id', 'oneway_flag'])

    for row in reader:
        way_id, highway, name, oneway, maxspeed_raw, refs_str = row
        refs = [int(x) for x in refs_str.split('|') if x]
        if len(refs) < 2:
            continue
        speed_kph = parse_maxspeed(maxspeed_raw, highway)
        oneway_norm = oneway.strip().lower()

        for i in range(len(refs) - 1):
            a, b = refs[i], refs[i + 1]
            if a not in node_coord or b not in node_coord:
                skipped_missing_coord += 1
                continue
            lat1, lon1 = node_coord[a]
            lat2, lon2 = node_coord[b]
            length_m = haversine_m(lat1, lon1, lat2, lon2)
            if length_m == 0:
                continue
            travel_time_min = (length_m / 1000.0) / speed_kph * 60.0

            used_node_ids.add(a)
            used_node_ids.add(b)
            class_length_m[highway] = class_length_m.get(highway, 0.0) + length_m

            if oneway_norm in ONEWAY_FORWARD:
                writer.writerow([a, b, f'{length_m:.1f}', speed_kph, f'{travel_time_min:.3f}', highway, name, way_id, 'forward'])
                edge_count += 1
                fwd_only_count += 1
            elif oneway_norm in ONEWAY_REVERSE:
                writer.writerow([b, a, f'{length_m:.1f}', speed_kph, f'{travel_time_min:.3f}', highway, name, way_id, 'reverse'])
                edge_count += 1
                rev_only_count += 1
            else:
                writer.writerow([a, b, f'{length_m:.1f}', speed_kph, f'{travel_time_min:.3f}', highway, name, way_id, 'bidir'])
                writer.writerow([b, a, f'{length_m:.1f}', speed_kph, f'{travel_time_min:.3f}', highway, name, way_id, 'bidir'])
                edge_count += 2
                bidir_count += 1

with open(OUT_NODES, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['node_id', 'lat', 'lon'])
    for nid in used_node_ids:
        lat, lon = node_coord[nid]
        writer.writerow([nid, f'{lat:.7f}', f'{lon:.7f}'])

print(f"DONE in {time.time()-t0:.1f}s")
print(f"Graph nodes (used by kept edges): {len(used_node_ids)}")
print(f"Directed edges written: {edge_count}  (from {bidir_count} bidir way-segments, "
      f"{fwd_only_count} forward-only, {rev_only_count} reverse-only)")
print(f"Segments skipped for missing coords: {skipped_missing_coord}")
print()
print("Total road length by class (km):")
for cls, m in sorted(class_length_m.items(), key=lambda x: -x[1]):
    print(f"  {cls:16s} {m/1000:8.1f} km")
